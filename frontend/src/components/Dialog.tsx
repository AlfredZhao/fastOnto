import { useEffect, useId, useRef } from 'react';

export default function Dialog({ open, title, onCancel, onConfirm, message = '当前草稿尚未保存。继续会替换编辑区内容；可先取消并导出 YAML。', confirmLabel = '放弃草稿并打开', confirmDisabled = false }: {open: boolean; title: string; onCancel: () => void; onConfirm: () => void; message?: string; confirmLabel?: string; confirmDisabled?: boolean}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { if (open) ref.current?.showModal(); else ref.current?.close(); }, [open]);
  return <dialog ref={ref} aria-labelledby={titleId} onCancel={event => { event.preventDefault(); onCancel(); }}>
    <h2 id={titleId}>{title}</h2><p>{message}</p>
    <div className="actions"><button onClick={onCancel}>保留草稿</button><button className="danger" disabled={confirmDisabled} onClick={onConfirm}>{confirmLabel}</button></div>
  </dialog>;
}
