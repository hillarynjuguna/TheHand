import hashlib
import json
import re
from collections import Counter
from typing import Dict, Iterable, List, Optional

MAX_DIMENSIONS = 2048
TOKEN_RE = re.compile(r"[a-z0-9']+", re.IGNORECASE)


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9\s']+", ' ', text.lower())


def tokenize(text: str) -> List[str]:
    normalized = normalize_text(text)
    return [token for token in TOKEN_RE.findall(normalized) if len(token) > 1]


def _hash_token(token: str, dimensions: int = MAX_DIMENSIONS) -> int:
    digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
    return int.from_bytes(digest, 'little') % dimensions


def build_embedding(text: str, dimensions: int = MAX_DIMENSIONS) -> List[float]:
    tokens = tokenize(text)
    if not tokens:
        return [0.0] * dimensions

    counts = Counter(tokens)
    vector = [0.0] * dimensions
    for token, count in counts.items():
        index = _hash_token(token, dimensions)
        vector[index] += float(count)

    norm = sum(value * value for value in vector) ** 0.5
    if norm > 0:
        vector = [value / norm for value in vector]
    return vector


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if len(a_list) != len(b_list):
        return 0.0
    numerator = sum(x * y for x, y in zip(a_list, b_list))
    if numerator == 0.0:
        return 0.0
    return numerator


def _parse_segments(json_text: str) -> List[Dict[str, Optional[float]]]:
    try:
        data = json.loads(json_text)
    except Exception:
        return []

    segments = []
    candidate = None
    if isinstance(data, dict):
        candidate = data.get('segments')
    if not isinstance(candidate, list):
        return []

    for item in candidate:
        if not isinstance(item, dict):
            continue
        text = item.get('text') or item.get('sentence') or ''
        start = item.get('start')
        end = item.get('end')
        if not text or start is None or end is None:
            continue
        segments.append({'text': str(text).strip(), 'start': float(start), 'end': float(end)})
    return segments


def chunk_transcript(text: str, json_raw: Optional[str] = None, max_words: int = 160, max_seconds: float = 35.0, max_gap: float = 4.0) -> List[Dict[str, Optional[object]]]:
    segments = []
    if json_raw:
        segments = _parse_segments(json_raw)

    if segments:
        chunks = []
        current = {'text': '', 'start': None, 'end': None, 'word_count': 0}
        for segment in segments:
            segment_text = segment['text'].strip()
            if not segment_text:
                continue
            segment_words = len(tokenize(segment_text))
            if current['start'] is None:
                current.update({'text': segment_text, 'start': segment['start'], 'end': segment['end'], 'word_count': segment_words})
                continue

            gap = segment['start'] - (current['end'] or segment['start'])
            chunk_duration = (segment['end'] - current['start']) if current['start'] is not None else 0
            if (
                current['word_count'] + segment_words > max_words
                or chunk_duration >= max_seconds
                or gap > max_gap
            ):
                chunks.append({
                    'text': current['text'].strip(),
                    'start_ts': current['start'],
                    'end_ts': current['end'],
                })
                current = {'text': segment_text, 'start': segment['start'], 'end': segment['end'], 'word_count': segment_words}
                continue

            current['text'] += ' ' + segment_text
            current['end'] = segment['end']
            current['word_count'] += segment_words

        if current['text']:
            chunks.append({
                'text': current['text'].strip(),
                'start_ts': current['start'],
                'end_ts': current['end'],
            })
        return chunks

    # Fallback segmentation by approximate word groups
    tokens = text.split()
    if not tokens:
        return []

    chunks = []
    current_tokens = []
    start = 0
    for index, token in enumerate(tokens):
        current_tokens.append(token)
        if len(current_tokens) >= max_words:
            chunk_text = ' '.join(current_tokens).strip()
            chunks.append({'text': chunk_text, 'start_ts': None, 'end_ts': None})
            current_tokens = []
    if current_tokens:
        chunks.append({'text': ' '.join(current_tokens).strip(), 'start_ts': None, 'end_ts': None})
    return chunks


def parse_similarity_candidates(value: Optional[str]) -> List[float]:
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []
