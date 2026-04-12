import { ChevronDown } from "lucide-react";
import React from "react";

type SelectProps = React.SelectHTMLAttributes<HTMLSelectElement> & {
  wrapperClassName?: string;
  iconClassName?: string;
};

const cx = (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(" ");

export const AppSelect: React.FC<SelectProps> = ({
  className,
  wrapperClassName,
  iconClassName,
  children,
  ...props
}) => {
  return (
    <div className={cx("relative", wrapperClassName)}>
      <select {...props} className={cx("select", className)}>
        {children}
      </select>
      <ChevronDown
        className={cx(
          "pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400",
          iconClassName,
        )}
        strokeWidth={2.25}
      />
    </div>
  );
};

export default AppSelect;
