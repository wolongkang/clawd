import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from apis import fal_api, haiku, openai_api, pexels, tts, youtube_upload
from utils.video import composite_video, composite_slides_video, create_ken_burns_clips

logger = logging.getLogger(__name__)

TMP_BASE = "/tmp/videobot/youtube"

WORDS_PER_MINUTE = 150


def _get_work_dir(user_id: int) -> str:
    """Get a unique working directory per user to avoid file conflicts."""
    path = os.path.join(TMP_BASE, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def _cleanup(work_dir: str, keep_final: str = None):
    """Clean up temp files after upload. Keep final video if YouTube upload pending."""
    try:
        for f in os.listdir(work_dir):
            fpath = os.path.join(work_dir, f)
            if keep_final and os.path.abspath(fpath) == os.path.abspath(keep_final):
                continue
            if os.path.isfile(fpath):
                os.remove(fpath)
        logger.info(f"Cleaned up {work_dir}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


async def handle(query, context: ContextTypes.DEFAULT_TYPE, minutes: int):
    topic = context.user_data.get("topic", "")
    user_id = query.from_user.id
    work_dir = _get_work_dir(user_id)

    # 1. Structured script with chapters (Haiku)
    await query.edit_message_text(f"[1/5] Writing {minutes}m structured script...")
    script_data = await haiku.generate_youtube_script_structured(topic, minutes)

    if not script_data or "chapters" not in script_data:
        # Fallback to legacy flat script + stock footage pipeline
        logger.warning("Structured script failed, falling back to legacy pipeline")
        await _handle_legacy(query, context, minutes, topic, work_dir)
        return

    chapters = script_data["chapters"]
    # Build full narration text for TTS
    full_narration = "\n\n".join(ch.get("narration", "") for ch in chapters)
    word_count = len(full_narration.split())
    await query.edit_message_text(
        f"[1/5] Script ready: {len(chapters)} chapters, {word_count} words (~{word_count // WORDS_PER_MINUTE}m)"
    )

    # 2. Audio (ElevenLabs)
    await query.edit_message_text(f"[2/5] Generating voiceover (ElevenLabs)...")
    audio = await tts.generate_speech(full_narration, target_minutes=minutes)
    if not audio:
        await query.edit_message_text("Audio generation failed.")
        context.user_data["mode"] = None
        return

    audio_path = os.path.join(work_dir, "audio.mp3")
    with open(audio_path, "wb") as f:
        f.write(audio)

    # 3. Generate AI slide images (Nano Banana Pro)
    await query.edit_message_text(f"[3/5] Generating {len(chapters)} slide images...")
    slide_urls = []

    for i, ch in enumerate(chapters):
        await query.edit_message_text(
            f"[3/5] Generating slide {i+1}/{len(chapters)}: {ch.get('title', '')}..."
        )
        url = await fal_api.generate_slide(ch.get("visual", f"Professional cinematic image about {topic}"))
        if url:
            slide_urls.append(url)
        else:
            logger.warning(f"Slide {i+1} failed, will use placeholder")
            # Try a simpler prompt as fallback
            url = await fal_api.generate_slide(
                f"Cinematic 16:9 photorealistic scene about {ch.get('title', topic)}, "
                f"professional lighting, high detail"
            )
            if url:
                slide_urls.append(url)
            else:
                await query.edit_message_text(f"Slide generation failed at chapter {i+1}.")
                context.user_data["mode"] = None
                _cleanup(work_dir)
                return

    await query.edit_message_text(f"[3/5] All {len(slide_urls)} slides generated!")

    # 4. Ken Burns clips + crossfade + audio composite
    await query.edit_message_text("[4/5] Creating animated slides + compositing video...")

    # Calculate per-chapter duration based on word count proportions
    from utils.video import get_duration
    audio_dur = get_duration(audio_path)
    if audio_dur <= 0:
        await query.edit_message_text("Audio has zero duration.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    chapter_words = [len(ch.get("narration", "").split()) for ch in chapters]
    total_words = sum(chapter_words)
    if total_words <= 0:
        total_words = 1

    # Distribute audio duration proportionally by word count
    chapter_durations = [(w / total_words) * audio_dur for w in chapter_words]
    # Ensure minimum 3 seconds per chapter
    chapter_durations = [max(3.0, d) for d in chapter_durations]

    logger.info(f"Chapter durations: {[f'{d:.1f}s' for d in chapter_durations]}")

    # Create Ken Burns clips from slide images
    kb_clips = create_ken_burns_clips(slide_urls, chapter_durations, work_dir)
    if not kb_clips:
        logger.warning("Ken Burns clips failed, falling back to legacy pipeline")
        await query.edit_message_text("[4/5] Slide animation failed, using stock footage fallback...")
        await _handle_legacy_from_audio(query, context, minutes, topic, work_dir, audio_path, full_narration)
        return

    # Composite: crossfade slides + audio
    output_path = os.path.join(work_dir, "final_video.mp4")
    success = composite_slides_video(kb_clips, audio_path, output_path)

    if not success or not os.path.exists(output_path):
        await query.edit_message_text("Video composition failed.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    # 5. Deliver
    await _deliver_video(query, context, output_path, topic, full_narration, work_dir, minutes, chapters)


async def _handle_legacy(query, context, minutes, topic, work_dir):
    """Legacy pipeline: flat script + Pexels stock footage."""
    await query.edit_message_text(f"[1/4] Writing {minutes}m script (Haiku)...")
    script = await haiku.generate_youtube_script(topic, minutes)
    if not script:
        await query.edit_message_text("Script generation failed.")
        context.user_data["mode"] = None
        return

    word_count = len(script.split())
    await query.edit_message_text(f"[1/4] Script ready: {word_count} words (~{word_count // WORDS_PER_MINUTE}m)")

    await query.edit_message_text(f"[2/4] Generating audio (ElevenLabs)...")
    audio = await tts.generate_speech(script, target_minutes=minutes)
    if not audio:
        await query.edit_message_text("Audio generation failed.")
        context.user_data["mode"] = None
        return

    audio_path = os.path.join(work_dir, "audio.mp3")
    with open(audio_path, "wb") as f:
        f.write(audio)

    await _handle_legacy_from_audio(query, context, minutes, topic, work_dir, audio_path, script)


async def _handle_legacy_from_audio(query, context, minutes, topic, work_dir, audio_path, script):
    """Legacy pipeline continuation from audio step: stock footage + composite."""
    await query.edit_message_text("[3/4] Finding background footage...")
    keywords = await openai_api.extract_video_keywords(script, count=6)
    if not keywords:
        keywords = [topic]

    footage_urls = await pexels.get_footage_for_script(keywords, clips_per_keyword=2)
    if not footage_urls:
        footage_urls = await pexels.get_footage(topic, count=5)
    if not footage_urls:
        await query.edit_message_text("Could not find background footage.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    await query.edit_message_text(f"[3/4] Got {len(footage_urls)} background clips")
    await query.edit_message_text("[4/4] Compositing video (this takes a while)...")

    output_path = os.path.join(work_dir, "final_video.mp4")
    success = composite_video(footage_urls, None, audio_path, output_path)

    if not success or not os.path.exists(output_path):
        await query.edit_message_text("Video composition failed.")
        context.user_data["mode"] = None
        _cleanup(work_dir)
        return

    await _deliver_video(query, context, output_path, topic, script, work_dir, minutes)


async def _deliver_video(query, context, output_path, topic, script, work_dir, minutes, chapters=None):
    """Send video to Telegram + offer YouTube upload."""
    context.user_data["last_video_path"] = output_path
    context.user_data["last_video_topic"] = topic
    context.user_data["last_video_script"] = script
    context.user_data["last_video_chapters"] = chapters

    file_size = os.path.getsize(output_path)
    size_mb = file_size / (1024 * 1024)

    chat_id = query.message.chat_id

    if file_size <= 50 * 1024 * 1024:
        await query.edit_message_text(f"[5/5] Uploading {size_mb:.0f}MB to Telegram...")
        with open(output_path, "rb") as f:
            await context.bot.send_video(
                chat_id=chat_id,
                video=f.read(),
                caption=f"{minutes}m YouTube Video - {topic}",
            )
        await query.delete_message()
    else:
        await query.edit_message_text(
            f"Video is {size_mb:.0f}MB (exceeds Telegram 50MB limit).\n"
            f"Saved at: {output_path}"
        )

    _cleanup(work_dir, keep_final=output_path)

    if youtube_upload.is_available():
        keyboard = [
            [InlineKeyboardButton("Public", callback_data="ytup_public"),
             InlineKeyboardButton("Unlisted", callback_data="ytup_unlisted"),
             InlineKeyboardButton("Private", callback_data="ytup_private")],
            [InlineKeyboardButton("Skip", callback_data="ytup_skip")],
        ]
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Upload to YouTube?\n({size_mb:.0f}MB, {topic})",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="YouTube upload not configured. Run youtube_auth.py to set it up.",
        )

    context.user_data["mode"] = None
