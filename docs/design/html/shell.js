/* ─────────────────────────────────────────────────────────────
   shell.js — 사이드바 / 상단바 / 아이콘 공용 렌더러
   각 페이지는 window.PAGE 설정 후 이 스크립트를 로드한다.
   PAGE = { nav:[{icon,label,active,children:[{label,active}]}],
            user:{name,team,avatar}, search:'placeholder', brand:'AI 상담 도우미' }
   본문 안에서는 <i class="ico" data-icon="home"></i> 로 아이콘 사용.
   ───────────────────────────────────────────────────────────── */
(function () {
  const S = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"';
  const svg = (inner, vb = '0 0 24 24', attrs = S) => `<svg viewBox="${vb}" ${attrs}>${inner}</svg>`;

  const ICONS = {
    home: svg('<path d="M3 11l9-8 9 8v9a2 2 0 0 1-2 2h-4v-7h-6v7H5a2 2 0 0 1-2-2z"/>'),
    'home-fill': svg('<path d="M3 11l9-8 9 8v9a2 2 0 0 1-2 2h-4v-7h-6v7H5a2 2 0 0 1-2-2z" fill="currentColor" stroke="currentColor"/><path d="M10 21v-6h4v6" fill="#fff" stroke="#fff" stroke-width="1"/>'),
    chat: svg('<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z"/><path d="M8 8h8M8 11.5h5"/>'),
    'chat-fill': svg('<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z" fill="currentColor"/><path d="M8 8h8M8 11.5h5" stroke="#fff"/>'),
    history: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>'),
    'history-fill': svg('<circle cx="12" cy="12" r="9" fill="currentColor"/><path d="M12 7v5l3.5 2" stroke="#fff" stroke-width="2"/>'),
    help: svg('<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.5"/><circle cx="12" cy="17" r=".6" fill="currentColor"/>'),
    search: svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
    'search-fill': svg('<circle cx="11" cy="11" r="7" fill="currentColor"/><circle cx="11" cy="11" r="3.5" fill="#fff" stroke="none"/><path d="M20 20l-3.5-3.5" stroke-width="2.5"/>'),
    bell: svg('<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20a2 2 0 0 0 4 0"/>'),
    'chevron-down': svg('<path d="M6 9l6 6 6-6"/>'),
    'chevron-right': svg('<path d="M9 6l6 6-6 6"/>'),
    'chevron-left': svg('<path d="M15 6l-6 6 6 6"/>'),
    'arrow-left': svg('<path d="M19 12H5M11 18l-6-6 6-6"/>'),
    'shield-check': svg('<path d="M12 3l7 3v5.5c0 4.5-3 8-7 9.5-4-1.5-7-5-7-9.5V6z"/><path d="M9 12l2 2 4-4"/>'),
    'shield-check-fill': svg('<path d="M12 3l7 3v5.5c0 4.5-3 8-7 9.5-4-1.5-7-5-7-9.5V6z" fill="currentColor"/><path d="M9 12l2 2 4-4" stroke="#fff" stroke-width="2"/>'),
    settings: svg('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
    send: svg('<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/>'),
    paperclip: svg('<path d="M21 11.5l-8.5 8.5a5 5 0 0 1-7-7l9-9a3.3 3.3 0 0 1 4.7 4.7l-9 9a1.7 1.7 0 0 1-2.4-2.4l8.3-8.3"/>'),
    refresh: svg('<path d="M20 11a8 8 0 0 0-14.5-4.5L4 8"/><path d="M4 3v5h5"/><path d="M4 13a8 8 0 0 0 14.5 4.5L20 16"/><path d="M20 21v-5h-5"/>'),
    'rotate-ccw': svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'),
    sparkles: svg('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" fill="currentColor" stroke="none"/><path d="M19 17l.8 2.2L22 20l-2.2.8L19 23l-.8-2.2L16 20l2.2-.8z" fill="currentColor" stroke="none"/><path d="M5 2l.6 1.6L7.2 4.2l-1.6.6L5 6.4l-.6-1.6L2.8 4.2l1.6-.6z" fill="currentColor" stroke="none"/>'),
    external: svg('<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>'),
    'file-text': svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>'),
    'file-fill': svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" fill="currentColor"/><path d="M14 3v5h5" stroke="#fff"/><path d="M9 13h6M9 17h6" stroke="#fff"/>'),
    'thumbs-up': svg('<path d="M7 11v9H4a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1z"/><path d="M7 11l4-7.5a2 2 0 0 1 3.7 1L14 9h5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.8 20H7"/>'),
    'thumbs-down': svg('<path d="M17 13V4h3a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1z"/><path d="M17 13l-4 7.5a2 2 0 0 1-3.7-1L10 15H5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.2 4H17"/>'),
    truck: svg('<path d="M3 6h11v10H3z"/><path d="M14 9h4l3 3v4h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>'),
    'credit-card': svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/>'),
    headset: svg('<path d="M4 13a8 8 0 0 1 16 0"/><path d="M4 13h2a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/><path d="M20 13h-2a1 1 0 0 0-1 1v4a1 1 0 0 0 1 1h1a1 1 0 0 0 1-1z"/><path d="M19 19v1a2 2 0 0 1-2 2h-4"/>'),
    'book-open': svg('<path d="M3 5h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H3z"/><path d="M21 5h-6a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h7z"/>'),
    'book-fill': svg('<path d="M3 5h6a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H3z" fill="currentColor"/><path d="M21 5h-6a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h7z" fill="currentColor"/>'),
    'bar-chart': svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
    'line-chart': svg('<path d="M3 20h18"/><path d="M4 16l5-5 4 3 6-7"/>'),
    'user-log': svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3"/><path d="M6.5 18.5a6 6 0 0 1 11 0"/>'),
    calendar: svg('<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>'),
    filter: svg('<path d="M4 6h16M7 12h10M10 18h4"/>'),
    sliders: svg('<path d="M4 8h10M18 8h2M4 16h4M12 16h8"/><circle cx="16" cy="8" r="2"/><circle cx="10" cy="16" r="2"/>'),
    upload: svg('<path d="M12 16V4"/><path d="M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>'),
    'cloud-upload': svg('<path d="M7 18a4.5 4.5 0 0 1-.7-8.9A6 6 0 0 1 18 8a4 4 0 0 1 .5 8"/><path d="M12 12v9"/><path d="M8.5 15.5L12 12l3.5 3.5"/>'),
    folder: svg('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
    'more-v': svg('<circle cx="12" cy="5" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="19" r="1.4" fill="currentColor"/>'),
    'more-h': svg('<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>'),
    eye: svg('<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
    edit: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>'),
    x: svg('<path d="M18 6L6 18M6 6l12 12"/>'),
    'x-circle': svg('<circle cx="12" cy="12" r="9"/><path d="M15 9l-6 6M9 9l6 6"/>'),
    check: svg('<path d="M5 12l5 5L20 7"/>'),
    'check-circle': svg('<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>'),
    'alert-circle': svg('<circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><circle cx="12" cy="16.5" r=".7" fill="currentColor"/>'),
    info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="8" r=".7" fill="currentColor"/>'),
    download: svg('<path d="M12 4v12"/><path d="M7 11l5 5 5-5"/><path d="M4 20h16"/>'),
    mail: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>'),
    phone: svg('<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>'),
    'message-square': svg('<path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4z"/>'),
    plus: svg('<path d="M12 5v14M5 12h14"/>'),
    'trending-up': svg('<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'),
    'pie-chart': svg('<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M12 3a9 9 0 0 1 9 9"/>'),
    'message-q': svg('<path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4z" fill="currentColor" stroke="none"/><path d="M10 9.5a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.2" stroke="#fff"/><circle cx="12" cy="14.5" r=".7" fill="#fff" stroke="none"/>'),
    'chat-fill-2': svg('<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z" fill="currentColor" stroke="none"/><path d="M8 8h8M8 11.5h5" stroke="#fff"/>'),
    'clock-fill': svg('<circle cx="12" cy="12" r="9" fill="currentColor" stroke="none"/><path d="M12 7v5l3.5 2" stroke="#fff" stroke-width="2"/>'),
    'user-circle-fill': svg('<circle cx="12" cy="12" r="9" fill="currentColor" stroke="none"/><circle cx="12" cy="10" r="3" stroke="#fff"/><path d="M6.5 18.5a6 6 0 0 1 11 0" stroke="#fff"/>'),
    'chart-fill': svg('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2" stroke-width="2.6"/>'),
    'target': svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/>'),
    'menu-search': svg('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
    'edit-doc': svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 15l5-5 2 2-5 5H9z"/>'),
    'headphones': svg('<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/>'),
    'gift': svg('<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v8h14v-8M12 8v12"/><path d="M12 8a3 3 0 1 1 3-3M12 8a3 3 0 1 0-3-3"/>'),
    'circle-dot': svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/>'),
    'radio-on': svg('<circle cx="12" cy="12" r="9" fill="none"/><circle cx="12" cy="12" r="4.5" fill="currentColor"/>'),
    'radio-off': svg('<circle cx="12" cy="12" r="9"/>'),
    'square-check': svg('<rect x="3" y="3" width="18" height="18" rx="4" fill="currentColor" stroke="none"/><path d="M7 12l3.5 3.5L17 9" stroke="#fff" stroke-width="2.2"/>'),
    'square': svg('<rect x="3.5" y="3.5" width="17" height="17" rx="4"/>'),
    'grid-list': svg('<path d="M4 6h16M4 12h16M4 18h16"/>'),
    'reset': svg('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'),
    'guide': svg('<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>'),
    'zap': svg('<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>'),
    'user-plus': svg('<circle cx="10" cy="8" r="4"/><path d="M2 21a8 8 0 0 1 16 0"/><path d="M19 8v6M16 11h6"/>'),
    'md': svg('<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 15V9l3 3 3-3v6M17 9v6M15 13l2 2 2-2"/>'),
    'html': svg('<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M14 5l-4 14"/>'),
  };

  window.icon = (name, cls = 'ico') => `<i class="${cls}" data-icon="${name}">${ICONS[name] || ''}</i>`;
  window.ICONS = ICONS;

  function renderShell() {
    const P = window.PAGE || {};
    const app = document.querySelector('.app');
    if (!app) return;
    if (/[?&]embed/.test(location.search)) document.body.classList.add('embed');
    const brand = P.brand || 'AI 상담 도우미';
    const user = P.user || { name: '김지원', team: '지원팀', avatar: 'assets/avatar-user.png' };
    const root = P.root || '';

    const navHtml = (P.nav || []).map(n => {
      const iconName = n.active && ICONS[n.icon + '-fill'] && !n.noFill ? n.icon + '-fill' : n.icon;
      let h = `<a class="nav-item${n.active ? ' active' : ''}" href="#">${icon(iconName)}<span>${n.label}</span></a>`;
      if (n.children) {
        h += `<ul class="nav-sub">${n.children.map(c => `<li class="${c.active ? 'active' : ''}">${c.label}</li>`).join('')}</ul>`;
      }
      return h;
    }).join('');

    const sidebar = `
      <aside class="sidebar">
        <div class="brand"><img src="${root}assets/logo-robot.png" alt=""><span>${brand}</span></div>
        <nav class="nav">${navHtml}</nav>
        <div class="sidebar-bottom">
          <div class="plan-card">
            <div class="plan-head">${icon('shield-check-fill')}<b>엔터프라이즈 플랜</b></div>
            <div class="plan-usage">사용량 <b>78%</b></div>
            <div class="plan-bar"><i></i></div>
          </div>
          <div class="admin-menu">${icon('settings')}<span>관리자 메뉴</span>${icon('chevron-down', 'ico chev')}</div>
        </div>
      </aside>`;

    const topbar = `
      <header class="topbar">
        <div class="top-search">${icon('search')}<span>${P.search || '문서, 상담 주제 검색 (예: 환불 정책)'}</span></div>
        <div class="top-right">
          <div class="status-pill">시스템 정상</div>
          <div class="top-divider"></div>
          <div class="bell">${icon('bell')}<span class="badge">3</span></div>
          <div class="top-divider" style="opacity:0"></div>
          <div class="profile">
            <img src="${root}${user.avatar || 'assets/avatar-user.png'}" alt="">
            <div><div class="p-name">${user.name}</div><div class="p-team">${user.team}</div></div>
            ${icon('chevron-down', 'ico chev')}
          </div>
        </div>
      </header>`;

    app.insertAdjacentHTML('afterbegin', sidebar + topbar);
    // 본문 내 아이콘 치환
    document.querySelectorAll('i[data-icon]').forEach(el => {
      if (!el.innerHTML.trim()) el.innerHTML = ICONS[el.dataset.icon] || '';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', renderShell);
  else renderShell();
})();
