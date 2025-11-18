import React from "react";

interface LabeledChipProps {
  label: string;
  value: React.ReactNode;
  variant?: "blue" | "gray" | "white";
}

export const LabeledChip: React.FC<LabeledChipProps> = ({ label, value, variant = "gray" }) => {
  const base = "px-2 py-0.5 rounded border text-[11px] inline-flex items-center gap-1";
  const cls =
    variant === "blue"
      ? `${base} bg-white border-blue-200 text-blue-700`
      : variant === "white"
      ? `${base} bg-white border-gray-200 text-gray-700`
      : `${base} bg-gray-100 border-gray-200 text-gray-700`;
  return (
    <span className={cls}>
      <span>{label}：</span>
      <span>{value}</span>
    </span>
  );
};

interface LabeledGroupProps {
  label: string;
  items: Array<string | number | React.ReactNode>;
  className?: string;
  itemClassName?: string;
}

export const LabeledGroup: React.FC<LabeledGroupProps> = ({ label, items, className, itemClassName }) => {
  return (
    <div className={`flex flex-wrap items-center gap-1 ${className || ""}`.trim()}>
      <span className="text-[11px] text-gray-600">{label}：</span>
      {items.map((item, idx) => (
        <span
          key={idx}
          className={`text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200 ${itemClassName || ""}`.trim()}
        >
          {item}
        </span>
      ))}
    </div>
  );
};

export default LabeledGroup;