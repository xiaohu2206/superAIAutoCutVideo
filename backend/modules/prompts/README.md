# Prompt directory layout

Each narration category owns an override area:

```text
backend/modules/prompts/<category>/
  script_generation/script_generation.md
  styles/<style_id>/<style_id>.md
```

Current categories:

- `short_drama_narration`
- `movie_narration`
- `tv_drama_narration`
- `variety_narration`
- `documentary_narration`
- `sports_narration`
- `general_narration`

For style prompts, empty files are placeholders. When a style markdown is empty,
the loader falls back to `backend/modules/prompts/common/<style_id>/<style_id>.md`
and adapts wording by narration type. Once you write content into a category
style file, that file becomes the official prompt for that category and style.

For the default `script_generation` prompt, empty files use the generic fallback
registered by `common/generic_script_generation_prompt.py`.
