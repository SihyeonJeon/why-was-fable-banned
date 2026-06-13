# fable-forge

**AI 코딩 에이전트에게 "spec 먼저" 규율을 강제하는 게이트.**
spec(재진술 목표·non-goals·권위 기반 컨텍스트·기각 대안·위험·실행가능 acceptance)을 쓰고
**게이트를 통과하기 전엔 코드 편집 차단.** Claude Code + Codex. 공유 게이트 1벌, CLI별 설치.

> `git clone https://github.com/SihyeonJeon/fable-forge && cd fable-forge && sh install.sh`

---

## 한눈에

- **무엇** — 에이전트가 *계획 없이* 코드 짜는 걸 막음. 변경마다 *의사결정 기록* 남김.
- **왜** — 세션 끝나면 에이전트 추론 증발. 급하면 spec·검증 생략. → 그 규율을 **비선택·감사가능**으로.
- **아닌 것** — *능력* 부스터 아님. 벤치 결과 *프로세스 강제*지 더 똑똑하게 만들진 않음([BENCHMARK](bench/BENCHMARK.md)).

---

## 설치

```sh
git clone https://github.com/SihyeonJeon/fable-forge
cd fable-forge
sh install.sh            # 자동감지 (claude-code | codex | all 명시 가능)
```
- 필요: `python3` (게이트는 stdlib only)
- 제거: `sh install.sh --uninstall`
- 끄기: `touch .forge/OFF` (프로젝트) · `FORGE_BYPASS=1` (1회)

---

## 동작

```
작업 프롬프트 → 게이트 task 자동 시작
            → 편집 시도 → BLOCKED (spec 미통과)
            → .forge/spec.json 작성 → 게이트 PASS → 편집 허용
            → acceptance 명령 실행 + 증거 기입 → done
```
질문·잡담 = 게이트 안 함 (토큰 0).

---

## 데이터 — 어떻게 수집·일반화·활용했나

이 게이트 룰은 추측이 아니라 **실제 AI 코딩 세션의 의사결정 기록**에서 뽑았다.

**① 수집** — `fable-pack`(레코더, hook 자동, 사적 추론 미수집·시크릿 마스킹·로컬 전용)
- *관측 가능한* 의사결정만 → 프로젝트별 `fable-disk/`
- **2층 기록**:
  | 층 | 잡은 것 | 방식 |
  |---|---|---|
  | 런타임 I/O | 프롬프트·파일읽기·명령+출력·편집·플랜·서브에이전트 호출 | hook 자동 |
  | 의사결정 출력 | 재진술 목표·컨텍스트 선정사유·**기각 대안**·위험·검증 증거 | 게이트 강제 |
- 규모: **7 프로젝트 / 42 trace** (19개 충실 채움)

**② 일반화** — 4 병렬 추출기 + **Codex 교차검증**
- 19 trace → **8축 의사결정 패턴**: 목표해석 · 컨텍스트선택 · 제약추출 · 대안분석 · 위험추론 · acceptance설계 · 검증루프 · 실패처리
- *도메인 횡단 수렴* = 일반화 / *단일도메인 산물* = 제외 (정량 교차검증으로 과장 정정)

**③ 활용** — 패턴 → 코드
- 8축 패턴을 **게이트 룰**(deterministic) + **룹릭**(LLM judge) + **체크리스트**(프롬프트)로 규격화
- `fable-forge`가 그걸 **runtime에서 강제** → 어떤 에이전트든 같은 spec-first 규율

---

## 3중 방어 (비용·깊이 증가)

| 레이어 | 검사 | 방식 | 범위 |
|---|---|---|---|
| `gates/forge_gate.py` | **형식** (필드·경로실존·forbidden·fail-closed) | deterministic, 무료 | 매 작업 |
| `gates/forge_judge.py` | **의미** (룹릭 0-2, 게이밍 탐지) | LLM judge, cross-family | HEAVY/코퍼스 ([JUDGE](JUDGE.md)) |
| `bench/` | **정확성** (숨은 채점기) | 테스트 실행 | 벤치 ([BENCHMARK](bench/BENCHMARK.md)) |

등급 자동화(LIGHT/STANDARD/HEAVY)로 토큰 절약 — LIGHT는 최소, 보안·결제·마이그만 풀 게이트.

---

## CLI별

**Claude Code** — `~/.claude/settings.json`에 훅 머지 (user-레벨 = 전 프로젝트·서브에이전트 상속)
- 편집 **in-session 하드차단** (훅 실제 발화, LIGHT <2× 토큰)

**Codex**
- 대화형(TUI): `/hooks` trust 후 작동
- headless `codex exec`: 훅 미발화(file_change 구조) → wrapper로 강제:
  ```sh
  forge-codex-accept "<goal>" --repo <dir>
  ```
  버리는 worktree서 작업 → **게이트 통과해야만 실 repo에 적용** (unspeced/forbidden 차단)
- 상세: [adapters/codex/ENFORCEMENT.md](adapters/codex/ENFORCEMENT.md)

---

## 정직 라벨

- "약한 모델 = 강한 모델"은 **벤치서 미입증** → 가치는 *프로세스·감사·안전*이지 능력 부스트 아님
- *관측 가능한 산출물*만 수집 (사적 추론·CoT 아님), 로컬 전용, 시크릿 마스킹
- 테스트 23개 (`bash tests/run_all.sh`) · MIT
