import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // NEXT_PUBLIC_API_URL 은 빌드 시점에 번들에 인라인된다.
  // 배포(Vercel)에서는 반드시 환경변수로 설정할 것 — 로컬 개발 기본값은 lib/api.ts 에서 처리한다.
};

export default nextConfig;
