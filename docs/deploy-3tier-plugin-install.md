> 원본: https://github.com/speeno/claude-plugins/blob/main/INSTALL.md (이 파일은 사본입니다. 수정은 원본에서.)

# deploy-3tier 플러그인 설치 가이드

`deploy-3tier`는 웹 프로젝트를 **프론트 Vercel · 백엔드 Render · DB Supabase Postgres** 3티어 무료 구성으로 전환하고 CLI만으로 배포해 주는 Claude Code 플러그인입니다. 이 문서는 **설치 → 확인 → 첫 실행 준비 → 업데이트/제거 → 문제 해결**을 순서대로 다룹니다.

---

## 1. 준비물

| 항목 | 확인 방법 | 비고 |
|---|---|---|
| Claude Code (플러그인 지원 버전) | `claude --version` | `/plugin` 명령이 있으면 OK |
| git | `git --version` | 마켓플레이스를 git clone으로 가져옴 |
| GitHub 접근 | SSH 키 **또는** HTTPS | `owner/repo` 단축 표기는 기본 SSH. SSH 키가 없으면 3-1의 HTTPS 방법 사용 |

배포 실행 단계에서 추가로 필요한 CLI(플러그인이 설치 여부를 점검하고 안내합니다):

```bash
npm i -g vercel                      # Vercel CLI
brew install render                  # Render CLI (macOS; 다른 OS는 https://render.com/docs/cli)
brew install supabase/tap/supabase   # Supabase CLI
brew install gh                      # GitHub CLI (선택: keep-alive 워크플로 실행/확인용)
```

---

## 2. 설치 (권장: 마켓플레이스)

### 2-1. Claude Code 세션 안에서

```
/plugin marketplace add speeno/claude-plugins
/plugin install deploy-3tier@speeno-plugins
```

1. 첫 줄: 마켓플레이스 `speeno-plugins`가 등록됩니다 (`✔ Successfully added marketplace: speeno-plugins`).
2. 둘째 줄: 플러그인 상세 화면이 열리면 **설치 범위**를 고릅니다.
   - `user` — 내 계정 전체(모든 프로젝트에서 사용). **일반적으로 이것**
   - `project` — 현재 리포에만(`.claude/settings.json`에 기록되어 팀원과 공유)
   - `local` — 현재 리포, 나만(`.claude/settings.local.json`)
3. 설치 요약에 `Run /reload-plugins to activate.`가 보이면 `/reload-plugins` 실행.

### 2-2. 터미널에서 (스크립트/비대화형)

```bash
claude plugin marketplace add speeno/claude-plugins
claude plugin install deploy-3tier@speeno-plugins --scope user    # user | project | local
```

### 2-3. SSH 키가 없을 때 (HTTPS로 받기)

```bash
CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1 claude plugin marketplace add speeno/claude-plugins
# 또는 URL 형태로
claude plugin marketplace add https://github.com/speeno/claude-plugins.git
```

---

## 3. 설치 확인

```bash
claude plugin list
```
```
  ❯ deploy-3tier@speeno-plugins
    Version: 1.0.0
    Scope: user
    Status: ✔ enabled
```

```bash
claude plugin details deploy-3tier@speeno-plugins     # Skills (1) deploy-3tier 가 보이면 정상
```

Claude Code 세션에서 `/help` → **Custom commands** 탭에 `/deploy-3tier:deploy-3tier`가 나타납니다. (플러그인 스킬은 `플러그인명:스킬명`으로 네임스페이스됩니다.)

---

## 4. 첫 실행 전 — 서비스 로그인 (사용자가 직접 하는 유일한 단계)

배포 대상 프로젝트 루트에서 터미널을 열고 세 CLI에 로그인합니다. 브라우저 승인 흐름이라 **에이전트가 대신할 수 없고**, 각각 1회만 하면 됩니다.

```bash
vercel login      # 브라우저 승인 → 터미널에 완료 표시
render login      # 브라우저에 "Authorize the Render CLI" → Authorize CLI 클릭 → 터미널에 "Login successful"
supabase login    # 브라우저에 8자리 코드가 뜸 → "Copy code" → 터미널의 "Enter your verification code:"에 붙여넣고 Enter → "Finished supabase login"
```

확인:
```bash
vercel whoami && render whoami && supabase orgs list
```
셋 다 정상 출력되면 준비 끝입니다. (Render 토큰은 7일 후 만료되어 `render login`을 다시 해야 할 수 있습니다.)

> 주의: `supabase login`은 브라우저 승인만으로 끝나지 않습니다. 코드를 **터미널에 다시 입력**해야 완료됩니다. 브라우저가 자동으로 열리지 않으면 `supabase login --no-browser`로 링크를 받아 직접 여세요.

---

## 5. 실행

프로젝트 루트에서 Claude Code를 열고:

```
/deploy-3tier:deploy-3tier
```
또는 자연어로 "프론트는 Vercel, 백엔드는 Render, DB는 Supabase로 무료 배포해줘".

플러그인이 수행하는 일(요약): CLI/로그인 점검 → 프로젝트 분석 → 코드 변경(`DATABASE_URL` Postgres 분기, Session Pooler, health의 DB 조회, CORS, `$PORT` 바인딩, 프론트 API URL env·콜드스타트 UX) → Supabase 프로젝트 생성 → Render 서비스 생성 → Vercel 배포 → CORS 마감 → E2E 검증 → keep-alive GitHub Action 추가 → `docs/deploy.md` 기록. 중간에 멈추는 경우는 로그인 미완료, 스코프/조직이 여러 개라 선택이 필요할 때, 기존 서비스 덮어쓰기 확인뿐입니다.

---

## 6. 팀 리포에서 자동 설치되게 하기 (선택)

프로젝트 리포의 `.claude/settings.json`에 추가해 커밋하면, 그 리포에서 Claude Code를 여는 팀원에게 마켓플레이스 등록과 플러그인 활성화가 자동 적용/안내됩니다.

```json
{
  "extraKnownMarketplaces": {
    "speeno-plugins": { "source": { "source": "github", "repo": "speeno/claude-plugins" } }
  },
  "enabledPlugins": { "deploy-3tier@speeno-plugins": true }
}
```

---

## 7. 업데이트 / 비활성화 / 제거

```
/plugin marketplace update speeno-plugins    # 카탈로그 갱신. 새 버전이 있으면 /plugin 화면에서 Update
/plugin disable deploy-3tier@speeno-plugins   # 잠시 끄기 (enable 로 복구)
/plugin uninstall deploy-3tier@speeno-plugins
/plugin marketplace remove speeno-plugins
```
터미널: `claude plugin marketplace update speeno-plugins`, `claude plugin disable|enable|uninstall deploy-3tier@speeno-plugins`.

---

## 8. 대안 설치 방법

| 방법 | 언제 | 명령 |
|---|---|---|
| 리포 clone 후 로컬 마켓플레이스 | 오프라인/사내망, 수정해서 쓰고 싶을 때 | `git clone https://github.com/speeno/claude-plugins.git` → `claude plugin marketplace add ./claude-plugins` → `claude plugin install deploy-3tier@speeno-plugins` |
| 세션 단위 로드(테스트) | 설치 없이 한 번 써보기 | `claude --plugin-dir ./claude-plugins/plugins/deploy-3tier` → `/deploy-3tier:deploy-3tier` |
| 스킬 파일만 복사 | 플러그인 시스템을 쓰지 않는 환경 | `plugins/deploy-3tier/skills/deploy-3tier/`를 `~/.claude/skills/deploy-3tier/`(개인) 또는 리포 `.claude/skills/deploy-3tier/`로 복사 → `/deploy-3tier`로 호출. 업데이트는 수동 |

---

## 9. 문제 해결

| 증상 | 원인 | 조치 |
|---|---|---|
| `marketplace add` 중 `Permission denied (publickey)` / clone 실패 | `owner/repo` 단축 표기가 SSH 사용 | `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1 …` 또는 `https://github.com/speeno/claude-plugins.git` |
| 같은 이름의 마켓플레이스가 이미 있다는 메시지 | 마켓플레이스 이름(`speeno-plugins`)은 사용자당 1개 | `/plugin marketplace remove speeno-plugins` 후 다시 add(기존 것이 교체됨) |
| 설치는 됐는데 `/deploy-3tier:deploy-3tier`가 안 보임 | 세션에 아직 로드되지 않음 | `/reload-plugins` 또는 Claude Code 재시작 |
| `/deploy-3tier`(콜론 없이)가 안 됨 | 플러그인 스킬은 네임스페이스 필수 | `/deploy-3tier:deploy-3tier` 사용 (스킬 파일 복사 방식일 때만 `/deploy-3tier`) |
| 실행 중 "run render login" / "Access token not provided" | 서비스 CLI 미로그인 | 4절대로 로그인(Supabase는 코드 입력까지) |
| 회사 정책으로 마켓플레이스 추가가 차단됨 | `strictKnownMarketplaces` 관리 설정 | 관리자에게 `speeno/claude-plugins` 허용 요청, 또는 8절 "스킬 파일만 복사" |
| 플러그인 구조가 의심될 때 | — | `claude plugin validate ./plugins/deploy-3tier` (`✔ Validation passed`) |

---

## 10. 참고

- 플러그인 소스/문서: https://github.com/speeno/claude-plugins
- 스킬 본문(절차·트러블슈팅 전체): `plugins/deploy-3tier/skills/deploy-3tier/SKILL.md`
- 레퍼런스 구현(FastAPI + Next.js, 이 절차로 실제 배포): https://github.com/speeno/RAG_CHATBOT — `docs/deploy.md`
- Claude Code 플러그인 공식 문서: https://code.claude.com/docs/en/discover-plugins , https://code.claude.com/docs/en/plugin-marketplaces
