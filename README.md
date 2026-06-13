# fable-forge

**AI 코딩 에이전트에게 "spec 먼저" 규율을 강제하는 게이트.**
spec(목표·non-goals·기각 대안·위험·acceptance)을 쓰고 통과하기 전엔 **코드 편집 차단.**
Claude Code + Codex.

> `git clone https://github.com/SihyeonJeon/fable-forge && cd fable-forge && sh install.sh`

---

## 한눈에

- **무엇** — 에이전트가 계획 없이 코드 짜는 걸 막고, 변경마다 의사결정 기록을 남김
- **왜** — 세션 끝나면 추론 증발 / 급하면 검증 생략 → 그 규율을 **비선택·감사가능**으로
- **아닌 것** — 능력 부스터 아님. *프로세스 강제*지 더 똑똑하게 만들진 않음

---

## 설치

```sh
git clone https://github.com/SihyeonJeon/fable-forge
cd fable-forge
sh install.sh
```
- 필요: `python3`
- 끄기: `touch .forge/OFF` · `FORGE_BYPASS=1` (1회) · 제거: `sh install.sh --uninstall`

---

## 동작

```
작업 프롬프트 → 게이트 자동 시작 → 편집 차단
            → .forge/spec.json 작성 → 통과 → 편집 허용 → 검증 → done
```
질문·잡담은 게이트 안 함.

---

## 데이터

게이트 룰은 추측이 아니라 **실제 코딩 세션의 의사결정 기록**에서 뽑음.

- **수집** — 세션의 *관측 가능한* 의사결정을 hook으로 자동 기록 (로컬·시크릿 마스킹, 사적 추론 미수집)
- **일반화** — 여러 세션의 공통 의사결정 패턴 추출 + 교차검증
- **활용** — 그 패턴을 게이트 룰·룹릭으로 코드화 → runtime 강제

---

## 구성

- `gates/` — 게이트 엔진(형식 검사) + 선택적 LLM judge(품질 검사)
- `adapters/` — Claude Code / Codex 설치
- `bench/`, `tests/` — 벤치·테스트 (23개, `bash tests/run_all.sh`)

로컬 전용 · 능력 향상은 미입증(가치는 프로세스·감사·안전) · MIT
