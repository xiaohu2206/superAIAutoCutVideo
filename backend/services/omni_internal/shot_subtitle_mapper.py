from typing import Any, Dict, List, Set

from services.omni_internal.types import Shot, Subtitle


class ShotSubtitleMapper:
    @staticmethod
    def split_subtitle_by_shots(subtitle: Subtitle, shots: List[Shot]) -> List[Dict[str, Any]]:
        result = []
        for shot in shots:
            overlap_start = max(subtitle.start, shot.start)
            overlap_end = min(subtitle.end, shot.end)
            if overlap_start < overlap_end:
                result.append(
                    {
                        "start": round(overlap_start, 3),
                        "end": round(overlap_end, 3),
                        "text": subtitle.text,
                        "original_subtitle_index": subtitle.index,
                    }
                )
        return result

    @staticmethod
    def map_subtitles_to_shots(shots: List[Shot], subtitles: List[Subtitle]) -> List[Shot]:
        for shot in shots:
            shot.subtitles = []
        for subtitle in subtitles:
            split_subs = ShotSubtitleMapper.split_subtitle_by_shots(subtitle, shots)
            for split_sub in split_subs:
                for shot in shots:
                    if shot.start <= split_sub["start"] and shot.end >= split_sub["end"]:
                        shot.subtitles.append(split_sub)
                        break
        return shots

    @staticmethod
    def _subtitle_indices(shot: Shot) -> Set[int]:
        return {
            int(sub["original_subtitle_index"])
            for sub in shot.subtitles or []
            if sub.get("original_subtitle_index") is not None
        }

    @staticmethod
    def _shared_coverage_ratio(shot: Shot, shared_indices: Set[int]) -> float:
        if not shot.subtitles:
            return 0.0
        shot_duration = max(shot.end - shot.start, 0.001)
        shared_duration = sum(
            max(sub["end"] - sub["start"], 0.0)
            for sub in shot.subtitles
            if sub.get("original_subtitle_index") in shared_indices
        )
        return shared_duration / shot_duration

    @staticmethod
    def _can_merge_adjacent(
        current_shot: Shot,
        next_shot: Shot,
        segment_start: float,
        min_overlap_ratio: float,
        short_shot_threshold: float,
        max_segment_duration: float,
    ) -> bool:
        if not current_shot.subtitles or not next_shot.subtitles:
            return False
        current_indices = ShotSubtitleMapper._subtitle_indices(current_shot)
        next_indices = ShotSubtitleMapper._subtitle_indices(next_shot)
        shared_indices = current_indices & next_indices
        if not shared_indices:
            return False
        current_is_short = (current_shot.end - current_shot.start) <= short_shot_threshold
        next_is_short = (next_shot.end - next_shot.start) <= short_shot_threshold
        current_coverage = ShotSubtitleMapper._shared_coverage_ratio(current_shot, shared_indices)
        next_coverage = ShotSubtitleMapper._shared_coverage_ratio(next_shot, shared_indices)
        coverage_ok = current_coverage >= min_overlap_ratio or next_coverage >= min_overlap_ratio
        if not (current_is_short or next_is_short or coverage_ok):
            return False
        if (next_shot.end - segment_start) > max_segment_duration:
            return False
        return True

    @staticmethod
    def _deduplicate_subtitles(subtitles: List[Dict[str, Any]], merge_by_index: bool = False) -> List[Dict[str, Any]]:
        if not subtitles:
            return []
        if merge_by_index:
            grouped: Dict[int, Dict[str, Any]] = {}
            non_indexed: List[Dict[str, Any]] = []
            for sub in subtitles:
                idx = sub.get("original_subtitle_index")
                if idx is None:
                    non_indexed.append(sub)
                    continue
                if idx not in grouped:
                    grouped[idx] = {
                        "start": sub["start"],
                        "end": sub["end"],
                        "text": sub["text"],
                        "original_subtitle_index": idx,
                    }
                    continue
                grouped[idx]["start"] = min(grouped[idx]["start"], sub["start"])
                grouped[idx]["end"] = max(grouped[idx]["end"], sub["end"])
            merged = list(grouped.values())
            merged.extend(non_indexed)
            return sorted(merged, key=lambda x: x["start"])
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for sub in subtitles:
            sub_key = (
                round(sub["start"], 3),
                round(sub["end"], 3),
                sub["text"],
                sub.get("original_subtitle_index"),
            )
            if sub_key in seen:
                continue
            deduped.append(sub)
            seen.add(sub_key)
        return sorted(deduped, key=lambda x: x["start"])

    @staticmethod
    def merge_shots_by_subtitle(
        shots: List[Shot],
        min_overlap_ratio: float = 0.4,
        short_shot_threshold: float = 3.0,
        max_segment_duration: float = 6.0,
    ) -> List[Shot]:
        if len(shots) <= 1:
            return shots
        merged_shots: List[Shot] = []
        i = 0
        while i < len(shots):
            current_shot = shots[i]
            if not current_shot.subtitles:
                merged_shots.append(current_shot)
                i += 1
                continue
            j = i + 1
            merge_candidates = [current_shot]
            merge_start = current_shot.start
            while j < len(shots):
                next_shot = shots[j]
                if not ShotSubtitleMapper._can_merge_adjacent(
                    current_shot,
                    next_shot,
                    merge_start,
                    min_overlap_ratio,
                    short_shot_threshold,
                    max_segment_duration,
                ):
                    break
                merge_candidates.append(next_shot)
                j += 1
                current_shot = Shot(
                    start=merge_start,
                    end=next_shot.end,
                    shot_id=current_shot.shot_id,
                    subtitles=[sub for candidate in merge_candidates for sub in (candidate.subtitles or [])],
                )
            if len(merge_candidates) > 1:
                merged_shot = Shot(
                    start=merge_candidates[0].start,
                    end=merge_candidates[-1].end,
                    shot_id=current_shot.shot_id,
                    subtitles=[sub for candidate in merge_candidates for sub in (candidate.subtitles or [])],
                )
                merged_shot.subtitles = ShotSubtitleMapper._deduplicate_subtitles(merged_shot.subtitles, merge_by_index=True)
                merged_shots.append(merged_shot)
                i = j
            else:
                merged_shots.append(current_shot)
                i += 1
        for idx, shot in enumerate(merged_shots, 1):
            shot.shot_id = idx
        return merged_shots

    @staticmethod
    def get_full_subtitle_text(shot: Shot) -> str:
        if not shot.subtitles:
            return ""
        sorted_subs = ShotSubtitleMapper._deduplicate_subtitles(shot.subtitles, merge_by_index=True)
        texts = [sub["text"] for sub in sorted_subs]
        return " ".join(texts)

    @staticmethod
    def build_semantic_segments(
        shots: List[Shot],
        min_overlap_ratio: float = 0.4,
        short_shot_threshold: float = 3.0,
        max_segment_duration: float = 6.0,
    ) -> List[Dict[str, Any]]:
        if not shots:
            return []
        segments: List[Dict[str, Any]] = []
        i = 0
        segment_id = 1
        while i < len(shots):
            current = Shot(
                start=shots[i].start,
                end=shots[i].end,
                shot_id=shots[i].shot_id,
                subtitles=list(shots[i].subtitles or []),
            )
            j = i + 1
            grouped = [shots[i]]
            segment_start = current.start
            while j < len(shots):
                next_shot = shots[j]
                if not ShotSubtitleMapper._can_merge_adjacent(
                    current,
                    next_shot,
                    segment_start,
                    min_overlap_ratio,
                    short_shot_threshold,
                    max_segment_duration,
                ):
                    break
                grouped.append(next_shot)
                current = Shot(
                    start=segment_start,
                    end=next_shot.end,
                    shot_id=current.shot_id,
                    subtitles=[sub for shot in grouped for sub in (shot.subtitles or [])],
                )
                j += 1
            all_subtitles = [sub for shot in grouped for sub in (shot.subtitles or [])]
            deduped_subtitles = ShotSubtitleMapper._deduplicate_subtitles(all_subtitles, merge_by_index=True)
            temp_shot = Shot(
                start=grouped[0].start,
                end=grouped[-1].end,
                shot_id=segment_id,
                subtitles=deduped_subtitles,
            )
            source_shots = [
                {
                    "shot_id": shot.shot_id,
                    "start": round(shot.start, 3),
                    "end": round(shot.end, 3),
                    "duration": round(shot.end - shot.start, 3),
                }
                for shot in grouped
            ]
            segments.append(
                {
                    "segment_id": segment_id,
                    "start": round(grouped[0].start, 3),
                    "end": round(grouped[-1].end, 3),
                    "duration": round(grouped[-1].end - grouped[0].start, 3),
                    "shot_ids": [shot.shot_id for shot in grouped],
                    "source_shots": source_shots,
                    "subtitles": deduped_subtitles,
                    "subtitle_full_text": ShotSubtitleMapper.get_full_subtitle_text(temp_shot),
                }
            )
            segment_id += 1
            i = j
        return segments

    @staticmethod
    def _pick_merge_target(prev_seg: Dict[str, Any], next_seg: Dict[str, Any]) -> str:
        prev_n = len(prev_seg.get("shot_ids") or [])
        next_n = len(next_seg.get("shot_ids") or [])
        if prev_n != next_n:
            return "prev" if prev_n < next_n else "next"
        prev_d = float(prev_seg.get("duration") or 0.0)
        next_d = float(next_seg.get("duration") or 0.0)
        return "prev" if prev_d <= next_d else "next"

    @staticmethod
    def _merge_two_segments(left: Dict[str, Any], right: Dict[str, Any], new_segment_id: int) -> Dict[str, Any]:
        shot_ids = list(left.get("shot_ids") or []) + list(right.get("shot_ids") or [])
        source_shots = list(left.get("source_shots") or []) + list(right.get("source_shots") or [])
        subtitles = list(left.get("subtitles") or []) + list(right.get("subtitles") or [])
        deduped_subtitles = ShotSubtitleMapper._deduplicate_subtitles(subtitles, merge_by_index=True)
        subtitle_full_text = " ".join([str(sub.get("text", "") or "") for sub in deduped_subtitles]).strip()
        start = min(float(left.get("start") or 0.0), float(right.get("start") or 0.0))
        end = max(float(left.get("end") or 0.0), float(right.get("end") or 0.0))
        return {
            "segment_id": new_segment_id,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "shot_ids": shot_ids,
            "source_shots": sorted(source_shots, key=lambda x: x.get("start", 0.0)),
            "subtitles": deduped_subtitles,
            "subtitle_full_text": subtitle_full_text,
        }

    @staticmethod
    def merge_short_segments_bidirectional(
        segments: List[Dict[str, Any]],
        short_segment_threshold: float = 3.0,
        max_segment_duration: float = 6.0,
    ) -> List[Dict[str, Any]]:
        if not segments:
            return []
        if len(segments) == 1:
            seg = dict(segments[0])
            seg["segment_id"] = 1
            return [seg]
        segs = [dict(s) for s in segments]
        changed = True
        while changed and len(segs) > 1:
            changed = False
            i = 0
            while i < len(segs):
                dur = float(segs[i].get("duration") or 0.0)
                if dur > short_segment_threshold:
                    i += 1
                    continue
                prev_idx = i - 1 if i - 1 >= 0 else None
                next_idx = i + 1 if i + 1 < len(segs) else None
                if prev_idx is None and next_idx is None:
                    i += 1
                    continue
                if prev_idx is None:
                    merged = ShotSubtitleMapper._merge_two_segments(segs[i], segs[next_idx], new_segment_id=0)
                    if float(merged["duration"]) <= max_segment_duration:
                        segs[i : next_idx + 1] = [merged]
                        changed = True
                        continue
                    i += 1
                    continue
                if next_idx is None:
                    merged = ShotSubtitleMapper._merge_two_segments(segs[prev_idx], segs[i], new_segment_id=0)
                    if float(merged["duration"]) <= max_segment_duration:
                        segs[prev_idx : i + 1] = [merged]
                        changed = True
                        i = max(prev_idx - 1, 0)
                        continue
                    i += 1
                    continue
                prev_seg = segs[prev_idx]
                next_seg = segs[next_idx]
                target = ShotSubtitleMapper._pick_merge_target(prev_seg, next_seg)

                def can_merge_with_prev() -> bool:
                    merged_prev = ShotSubtitleMapper._merge_two_segments(prev_seg, segs[i], new_segment_id=0)
                    return float(merged_prev["duration"]) <= max_segment_duration

                def can_merge_with_next() -> bool:
                    merged_next = ShotSubtitleMapper._merge_two_segments(segs[i], next_seg, new_segment_id=0)
                    return float(merged_next["duration"]) <= max_segment_duration

                if target == "prev":
                    if can_merge_with_prev():
                        merged = ShotSubtitleMapper._merge_two_segments(prev_seg, segs[i], new_segment_id=0)
                        segs[prev_idx : i + 1] = [merged]
                        changed = True
                        i = max(prev_idx - 1, 0)
                        continue
                    if can_merge_with_next():
                        merged = ShotSubtitleMapper._merge_two_segments(segs[i], next_seg, new_segment_id=0)
                        segs[i : next_idx + 1] = [merged]
                        changed = True
                        continue
                else:
                    if can_merge_with_next():
                        merged = ShotSubtitleMapper._merge_two_segments(segs[i], next_seg, new_segment_id=0)
                        segs[i : next_idx + 1] = [merged]
                        changed = True
                        continue
                    if can_merge_with_prev():
                        merged = ShotSubtitleMapper._merge_two_segments(prev_seg, segs[i], new_segment_id=0)
                        segs[prev_idx : i + 1] = [merged]
                        changed = True
                        i = max(prev_idx - 1, 0)
                        continue
                i += 1
        for new_id, seg in enumerate(segs, start=1):
            seg["segment_id"] = new_id
        return segs
