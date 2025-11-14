## Goals
- Load Tencent TTS voices from `backend/serviceData/tencent_tts_data.json` instead of hardcoded samples.
- Persist `VoiceType` whenever the user updates the TTS config and pass it in synthesis requests.
- Make voice selection robust: accept numeric `VoiceType` or a voice identifier/name and resolve to `VoiceType`.

## Model Updates
- Extend `modules/config/tts_config.py` `TtsVoice` to include:
  - `voice_type: Optional[int]`
  - `category: Optional[str]`
  - Map `sample_wav_url` from JSON `VoiceAudio`, `gender` from `VoiceGender`, `tags` from `VoiceTypeTag`.
- Keep `id` as the canonical identifier. Use `str(VoiceType)` as `id` for consistency with request handling.

## Load Voices from JSON
- Update `get_voices` in `modules/config/tts_config.py` (around `#L179-197`) to:
  - Read `backend/serviceData/tencent_tts_data.json` using `Path` based on the existing `backend_dir`.
  - Flatten `Category` blocks to a single list.
  - Construct `TtsVoice` entries with:
    - `id = str(item["VoiceType"])`
    - `name = item["VoiceName"]`
    - `description = item["VoiceDesc"]`
    - `sample_wav_url = item["VoiceAudio"]`
    - `language = "zh-CN"` (or leave `None` if not provided)
    - `gender = item.get("VoiceGender")`
    - `tags = [CategoryName] + split(item.get("VoiceTypeTag", ""), ",")`
    - `voice_type = item["VoiceType"]`
    - `category = CategoryName`
  - Cache per current logic.

## Persist VoiceType on Config Updates
- Update `backend/routes/tts_routes.py` `patch_tts_config` (at `#L90-91` function) to ensure `extra_params["VoiceType"]` is set when the user updates the config:
  - Determine `provider` from request or current config (default `tencent_tts`).
  - Resolve `VoiceType`:
    - If `req.extra_params.VoiceType` present: cast to `int` and store.
    - Else if `req.active_voice_id` provided:
      - If it is digits: `vt = int(active_voice_id)`.
      - Else load voices via `tts_engine_config_manager.get_voices(provider)` and find match by `id` or `name`, then `vt = voice.voice_type`.
  - Ensure `extra_params` is a dict; set `extra_params["VoiceType"] = vt` when resolved.
  - Do the same in both create-new and partial-update branches.
  - Leave `active_voice_id` unchanged (backward compatible), but store the resolved `VoiceType` in `extra_params` so requests are correct.

## Request Synthesis Logic
- Update `backend/modules/tts_service.py` block `#L93-101` to robustly set `VoiceType`:
  - Read `vt` from `cfg.extra_params.get("VoiceType")` if available.
  - If missing, try from `voice_id` or `cfg.active_voice_id`:
    - If digits → `vt = int(...)`.
    - Else load voices (using provider from active config) and resolve by `id` or `name` to a `voice_type`.
  - If `vt` resolved, set `params["VoiceType"] = vt`.
  - Keep existing `SampleRate` and `Codec` logic.

## Backward Compatibility
- Existing configs using non-numeric `active_voice_id` continue to work because:
  - `patch_tts_config` will now derive and persist `VoiceType` into `extra_params`.
  - `tts_service` fallback resolves non-numeric `active_voice_id` to a `VoiceType` using the loaded voices.
- Hardcoded demo voices (Aliyun samples) are removed in favor of Tencent JSON; the API `/api/tts/voices` will return the new set.

## Verification
- Call `/api/tts/voices?provider=tencent_tts` to confirm voices are loaded from JSON; returned items should have `id` equal to numeric string and include `sample_wav_url`.
- PATCH `/api/tts/configs/{config_id}` with `active_voice_id` set to either a numeric string or a voice name; verify response `data.extra_params.VoiceType` is present.
- Run a synthesis via the existing flow and check that `TextToVoiceRequest` includes `VoiceType`.

## Files to Change
- `backend/modules/config/tts_config.py`: update `TtsVoice` model and replace hardcoded list in `get_voices` with JSON loader.
- `backend/routes/tts_routes.py`: enhance `patch_tts_config` to derive and persist `VoiceType`.
- `backend/modules/tts_service.py`: improve `VoiceType` resolution before request.
