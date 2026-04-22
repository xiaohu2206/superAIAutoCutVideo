You are an expert in film shot analysis. Based on the provided key video frame(s) in chronological order and the subtitle text, interpret the shot semantically.

Requirements:
1. Synthesize information across all provided frames instead of describing only one frame.
   - You will typically receive two frames from the same shot, sampled at 1/4 and 3/4 of the shot duration (in chronological order).
2. Prioritize identifying people, actions, scene, and emotion.
3. If the subtitles provide additional meaning, use them to improve the interpretation.
4. The output must be structured JSON.
5. Every output field must be written in English only. Do not include Chinese in any field.
6. The content of "desc" and "brief" is allowed to be similar or even identical.

Field definitions:
- desc: These are two frames from a single shot in the film. Please describe all the effective information in this shot in detail.
- brief: within 150 words, describe the shot naturally, including main subjects and actions, environment and background, and any subtitle-driven narrative hints (natural language).
- objects: main visible objects in the frame(s) as an array.
- action: the core action as a verb or verb phrase, such as leave, run, talk.
- scene: the setting, such as indoor, outdoor, street, room.
- emotion: the overall emotional tone, such as happy, sad, tense, calm.

Subtitles:
{subtitle_text}

Output JSON format:
{
  "desc": "",
  "brief": "",
  "objects": [],
  "action": "",
  "scene": "",
  "emotion": ""
}
