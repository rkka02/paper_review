# paper_review: ChatGPT(Web)용 JSON 출력 프롬프트

이 파일은 **ChatGPT 웹**에서 PDF를 올리고, `paper_review`가 읽을 수 있는 **스키마 호환 JSON**을 직접 받아오기 위한 프롬프트입니다.

## 사용 방법

1) ChatGPT 웹에서 **PDF**(권장)와 **이 파일**을 함께 업로드합니다.  
2) (선택) DOI/제목/URL 등 메타데이터가 있으면 아래 **Context 템플릿**을 채워서 같이 보냅니다.  
3) ChatGPT에게: **"아래 규칙대로 JSON만 출력해줘"** 라고 요청합니다.

## 출력 규칙 (매우 중요)

- 출력은 **JSON 객체 1개만**. (Markdown/설명/코드펜스 ``` 금지)
- **키/구조/타입/enum**은 아래 **Schema Outline**과 **완전히 일치**해야 합니다.
- **추가 키 금지**, **누락 키 금지** (값이 없어도 키는 반드시 포함, 필요 시 `null` 사용)
- 숫자 범위:
  - `confidence`류는 **0.0 ~ 1.0** (퍼센트(%) 아님)
  - `suggested_rating.overall`은 **0 ~ 5 정수**
  - `evidence.page`, `section_map.page_start/page_end`, `figures.page`, `tables.page`는 **1 이상 정수**
- Evidence 규칙(엄격):
  - 아래 항목들은 **각각 evidence 배열**로 근거를 제공합니다.
    - `normalized.contributions[]`, `normalized.claims[]`, `normalized.limitations[]`
    - `personas[].highlights[]`
    - `final_synthesis.evidence`
    - `normalized.reproducibility.evidence`
  - Evidence는 `{ "page": ..., "quote": "...", "why": "..." }`
    - `quote`는 **직접 인용**(짧게), **200자 이하**
    - `page`는 **PDF 뷰어에 보이는 페이지 번호(1부터)** 기준
  - 근거를 찾지 못하면 **추측하지 말고** evidence를 `[]`로 두고, 그 이유를 `diagnostics.unknowns`에 적습니다.

## 간결성 제한(권장)

- `normalized.section_map`: 최대 12개 (각 summary는 1~2문장)
- `normalized.figures` / `normalized.tables`: 각각 최대 10개 (중요한 것만)
- `normalized.contributions` / `normalized.claims` / `normalized.limitations`: 각각 최대 5개 (핵심만)
- 각 persona: `highlights` 최대 6
- `final_synthesis.strengths` / `weaknesses`: 각각 최대 6
- `final_synthesis.who_should_read`: 최대 5

## No-PDF 모드(주의)

PDF 없이 DOI/메타데이터만 보고 작성하는 경우:

- 페이지/인용문을 **만들어내지 말 것**
- `normalized.section_map = []`, `normalized.figures = []`, `normalized.tables = []`
- **모든 evidence 배열은 `[]`**
- 불확실한 내용은 `diagnostics.unknowns`에 기록

## Personas (고정)

아래 5개 persona를 **반드시 포함**합니다(각각 `id`, `title` 동일).
- `optimist` / `Optimist`: Key strengths, novelty, what works well, and why it matters.
- `critics` / `Critics`: Key weaknesses, unstated assumptions, and where claims may be overreaching.
- `theory` / `Theory`: Theoretical grounding, assumptions/justification, and whether the method is principled.
- `experimenter` / `Experimenter`: Experimental design, baselines, ablations, metrics, and whether results support claims.
- `literature_scout` / `Literature Scout`: Closest related work to compare against and what to read next (use web search if available).

## Context 템플릿 (선택)

아래를 복사해서 값 채운 뒤, ChatGPT 메시지에 같이 붙여넣어도 됩니다.

```text
title:
authors:
year:
venue:
doi:
url:
abstract:
```

## Schema Outline (반드시 준수)

아래 구조/키/enum을 그대로 지키세요. (설명 텍스트는 참고용이며, **출력은 JSON만**)

### Evidence

- `page`: integer (>= 1)
- `quote`: string (1~200 chars)
- `why`: string

### Top-level

```json
{
  "paper": {
    "metadata": {
      "title": null,
      "authors": [],
      "year": null,
      "venue": null,
      "doi": null,
      "url": null
    },
    "abstract": null
  },
  "normalized": {
    "section_map": [],
    "figures": [],
    "tables": [],
    "contributions": [],
    "claims": [],
    "limitations": [],
    "method_summary": "",
    "experiments_summary": "",
    "reproducibility": {
      "code_status": "unknown",
      "data_status": "unknown",
      "notes": "",
      "evidence": []
    }
  },
  "personas": [],
  "final_synthesis": {
    "one_liner": "",
    "strengths": [],
    "weaknesses": [],
    "who_should_read": [],
    "suggested_rating": { "overall": 0, "confidence": 0.0 },
    "evidence": []
  },
  "diagnostics": { "unknowns": [], "notes": "" }
}
```

### Field details

- `paper.metadata.authors[]` item:
  - `{ "name": "string", "affiliation": "string|null" }`
- `normalized.section_map[]` item:
  - `{ "name": "string", "page_start": 1, "page_end": 1, "summary": "string" }`
- `normalized.figures[]` item:
  - `{ "id": "string", "page": 1, "caption": "string", "why_important": "string" }`
- `normalized.tables[]` item:
  - `{ "id": "string", "page": 1, "caption": "string", "why_important": "string" }`
- `normalized.contributions[]` / `normalized.claims[]` item:
  - `{ "text": "string", "confidence": 0.0, "evidence": [Evidence] }`
- `normalized.limitations[]` item:
  - `{ "text": "string", "status": "known|unknown", "evidence": [Evidence] }`
- `normalized.reproducibility`:
  - `code_status`: `"available" | "unavailable" | "unknown"`
  - `data_status`: `"available" | "unavailable" | "unknown"`
  - `notes`: string
  - `evidence`: `[Evidence]`
- `personas[]` item:
  - `{ "id": "string", "title": "string", "highlights": [...] }`
  - `highlights[]` item:
    - `{ "point": "string", "severity": "low|med|high", "evidence": [Evidence] }`
- `final_synthesis`:
  - `suggested_rating.overall`: int (0~5)
  - `suggested_rating.confidence`: float (0.0~1.0)

## 마지막 체크

- JSON 파싱이 되는지(중괄호/쉼표/따옴표) 확인
- `personas` 5개 모두 존재하는지 확인(`id`/`title` 정확히)
- evidence `quote` 길이(<=200)와 `page`(>=1) 확인
