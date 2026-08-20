"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Category, type Tag } from "@/lib/api";
import { Icon } from "@/components/Icon";

export function TaxonomyView() {
  const [cats, setCats] = useState<Category[] | null>(null);
  const [tags, setTags] = useState<Tag[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, t] = await Promise.all([api.listCategories(), api.listTags()]);
      setCats(c);
      setTags(t);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <>
      <div className="kb-head">
        <div>
          <h1 className="page-title">분류 관리</h1>
          <p className="page-sub">문서 카테고리와 태그를 관리합니다. 이름을 바꾸면 해당 분류를 쓰는 모든 문서에 일괄 반영됩니다.</p>
        </div>
        <button className="btn" onClick={load}><Icon name="refresh" /> 새로고침</button>
      </div>

      {error && <div className="alert error" style={{ marginBottom: 14 }}><Icon name="alert-circle" /> {error}</div>}

      <div className="tx-grid">
        <section className="card panel">
          <div className="panel-head"><h3>카테고리</h3><span className="muted">{cats?.length ?? 0}개</span></div>
          <div className="tx-add">
            <input className="input" placeholder="새 카테고리 이름 (예: policy)" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <input className="input" placeholder="설명 (선택)" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
            <button className="btn primary" disabled={!newName.trim()} onClick={() => run(async () => { await api.createCategory(newName.trim(), newDesc.trim() || null); setNewName(""); setNewDesc(""); })}>추가</button>
          </div>
          {cats === null ? <div className="empty-state"><span className="spinner" /> 불러오는 중…</div> : cats.length === 0 ? (
            <div className="empty-state">카테고리가 없습니다. 위에서 추가하거나 문서 업로드 시 지정하세요.</div>
          ) : (
            <div className="table-wrap">
              <table className="table tx-table">
                <thead><tr><th>이름</th><th>설명</th><th className="num">문서 수</th><th>등록</th><th style={{ textAlign: "right" }}>작업</th></tr></thead>
                <tbody>
                  {cats.map((c) => (
                    <tr key={c.name}>
                      {editing === c.name ? (
                        <>
                          <td><input className="input sm" value={editName} onChange={(e) => setEditName(e.target.value)} /></td>
                          <td><input className="input sm" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} placeholder="설명" /></td>
                          <td className="num">{c.doc_count}</td>
                          <td />
                          <td className="acts-r">
                            <button className="btn sm primary" onClick={() => run(async () => {
                              await api.patchCategory(c.name, { new_name: editName.trim() !== c.name ? editName.trim() : undefined, description: editDesc.trim() || null });
                              setEditing(null);
                            })}>저장</button>
                            <button className="btn sm" onClick={() => setEditing(null)}>취소</button>
                          </td>
                        </>
                      ) : (
                        <>
                          <td><b>{c.name}</b></td>
                          <td className="muted">{c.description ?? "-"}</td>
                          <td className="num">{c.doc_count}</td>
                          <td>{c.registered ? <span className="badge blue">등록됨</span> : <span className="badge gray" title="문서에서만 사용 중(카테고리 정보 미등록)">사용 중</span>}</td>
                          <td className="acts-r">
                            <button className="icon-btn" title="이름/설명 수정" onClick={() => { setEditing(c.name); setEditName(c.name); setEditDesc(c.description ?? ""); }}><Icon name="file-text" /></button>
                            <button className="icon-btn danger" title="삭제" onClick={() => {
                              const others = cats.filter((x) => x.name !== c.name).map((x) => x.name);
                              const to = c.doc_count > 0 && others.length > 0
                                ? prompt(`'${c.name}' 카테고리 문서 ${c.doc_count}건을 어느 카테고리로 옮길까요?\n(비우면 '미분류'로) 가능한 값: ${others.join(", ")}`, "") : "";
                              if (to === null) return;
                              run(() => api.deleteCategory(c.name, (to ?? "").trim() || null));
                            }}><Icon name="trash" /></button>
                          </td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="card panel">
          <div className="panel-head"><h3>태그</h3><span className="muted">{tags?.length ?? 0}개 · 업로드/문서 수정 시 부여</span></div>
          {tags === null ? <div className="empty-state"><span className="spinner" /> 불러오는 중…</div> : tags.length === 0 ? (
            <div className="empty-state">태그가 없습니다. 문서 업로드 폼의 "태그" 입력(쉼표 구분)으로 부여하세요.</div>
          ) : (
            <div className="tag-list">
              {tags.map((t) => (
                <div className="tag-item" key={t.name}>
                  <span className="chip">{t.name}</span>
                  <span className="muted">{t.doc_count}건</span>
                  <button className="icon-btn" title="이름 변경" onClick={() => {
                    const nn = prompt(`'${t.name}' 태그의 새 이름`, t.name);
                    if (nn && nn.trim() && nn.trim() !== t.name) run(() => api.renameTag(t.name, nn.trim()));
                  }}><Icon name="file-text" /></button>
                  <button className="icon-btn danger" title="모든 문서에서 제거" onClick={() => {
                    if (confirm(`'${t.name}' 태그를 ${t.doc_count}개 문서에서 제거할까요?`)) run(() => api.deleteTag(t.name));
                  }}><Icon name="trash" /></button>
                </div>
              ))}
            </div>
          )}
          <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>태그는 문서에 저장된 값에서 집계됩니다. 지식베이스 검색창에서 태그로도 검색됩니다.</div>
        </section>
      </div>
    </>
  );
}
