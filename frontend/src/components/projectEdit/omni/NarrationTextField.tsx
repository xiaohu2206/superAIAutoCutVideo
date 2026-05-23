import React from "react";

export interface NarrationTextFieldProps {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}

const NarrationTextField: React.FC<NarrationTextFieldProps> = ({ value, disabled, onChange }) => {
  const ref = React.useRef<HTMLTextAreaElement>(null);
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(value);

  React.useEffect(() => {
    if (!editing) setDraft(value);
  }, [editing, value]);

  const syncHeight = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  React.useLayoutEffect(() => {
    if (editing) syncHeight();
  }, [syncHeight, draft, editing]);

  React.useEffect(() => {
    if (!editing) return;
    const el = ref.current;
    if (!el) return;
    el.focus();
    const len = el.value.length;
    el.setSelectionRange(len, len);
  }, [editing]);

  React.useEffect(() => {
    if (disabled) setEditing(false);
  }, [disabled]);

  const displayText = value.trim() || "—";

  if (disabled) {
    return (
      <span className="block text-xs text-gray-500 dark:text-gray-400 leading-snug break-words whitespace-pre-wrap">
        {displayText}
      </span>
    );
  }

  if (!editing) {
    return (
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation();
          setDraft(value);
          setEditing(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            e.stopPropagation();
            setDraft(value);
            setEditing(true);
          }
        }}
        className="block w-full text-xs text-gray-900 dark:text-gray-100 leading-snug break-words whitespace-pre-wrap cursor-text rounded px-1.5 py-0.5 min-h-[22px] hover:bg-gray-50 dark:hover:bg-gray-800/60"
      >
        {displayText}
      </span>
    );
  }

  return (
    <textarea
      ref={ref}
      rows={1}
      value={draft}
      onChange={(e) => {
        const next = e.target.value;
        setDraft(next);
        onChange(next);
      }}
      onInput={syncHeight}
      onBlur={() => {
        if (draft !== value) onChange(draft);
        setEditing(false);
      }}
      onClick={(e) => e.stopPropagation()}
      className="w-full resize-none overflow-hidden min-h-[22px] py-0.5 px-1.5 text-xs leading-snug text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-600 rounded focus:ring-1 focus:ring-blue-500 focus:border-transparent outline-none"
    />
  );
};

export default NarrationTextField;
