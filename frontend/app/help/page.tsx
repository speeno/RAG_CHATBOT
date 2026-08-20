import Link from "next/link";

export const metadata = { title: "도움말 — AI 상담 도우미" };

export default function HelpPage() {
  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">도움말</h1>
          <p className="page-sub">AI 상담 도우미 이용 방법과 자주 묻는 질문입니다.</p>
        </div>
      </div>
      <div className="help-grid">
        <section className="card panel">
          <h3>AI 상담 도우미란?</h3>
          <p>관리자가 등록한 <b>공식 문서만을 근거로</b> 답변하는 상담 챗봇입니다. 모든 답변에는 출처 문서가 함께 표시되며,
            등록된 자료에서 근거를 찾지 못하면 추측으로 답하지 않고 <b>담당자 문의를 안내</b>합니다(Fail-Closed 원칙).</p>
        </section>
        <section className="card panel">
          <h3>이용 방법</h3>
          <ol className="help-steps">
            <li><Link className="link" href="/">상담하기</Link>에서 궁금한 내용을 자연어로 질문하세요. 추천 질문을 눌러도 됩니다.</li>
            <li>답변 아래의 <b>출처 카드</b>에서 근거 문서(버전·업데이트일)를 확인할 수 있습니다.</li>
            <li>같은 대화에서 이어서 질문하면 앞선 맥락을 반영해 검색합니다. (예: “그럼 배송비는?”)</li>
            <li>답변이 도움이 됐는지 👍/👎로 알려주세요. 👎 선택 시 사유·의견을 남기고 <b>상담원에게 전달</b>할 수 있습니다.</li>
            <li>지난 대화는 <Link className="link" href="/history">상담 이력</Link>에서 다시 보거나 이어서 진행할 수 있습니다.</li>
          </ol>
        </section>
        <section className="card panel">
          <h3>자주 묻는 질문</h3>
          <dl className="help-faq">
            <dt>답변 대신 “확인할 수 없습니다”가 나와요.</dt>
            <dd>질문과 충분히 관련된 문서가 등록되어 있지 않은 경우입니다. <b>상담원 연결</b>·<b>문의 남기기</b>로 접수하시면 담당자가 확인합니다. 다른 표현으로 다시 질문해 보셔도 좋습니다.</dd>
            <dt>첫 응답이 유난히 느려요.</dt>
            <dd>무료 호스팅 특성상 서버가 유휴 상태에서 깨어나는 데 최대 1분이 걸릴 수 있습니다. 화면에 “서버를 깨우는 중” 안내가 표시됩니다.</dd>
            <dt>상담 이력은 어디에 저장되나요?</dt>
            <dd>이력 목록은 사용 중인 브라우저에만 저장됩니다(최대 50건). 다른 기기·브라우저에서는 보이지 않습니다.</dd>
            <dt>개인정보를 입력해도 되나요?</dt>
            <dd>상담에 꼭 필요한 경우가 아니라면 전화번호·계좌번호 등 개인정보 입력은 피해주세요.</dd>
          </dl>
        </section>
      </div>
    </>
  );
}
