import React, { useState, useRef, useEffect } from 'react';

interface DropdownItem {
  label: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
}

interface DropdownProps {
  trigger: React.ReactNode;
  items: DropdownItem[];
  className?: string;
  menuClassName?: string;
  disabled?: boolean;
}

export const Dropdown: React.FC<DropdownProps> = ({ 
  trigger, 
  items, 
  className = '',
  menuClassName = '',
  disabled = false
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (disabled && isOpen) {
      setIsOpen(false);
    }
  }, [disabled, isOpen]);

  return (
    <div className={`relative inline-block text-left ${className}`} ref={ref}>
      <div
        onClick={() => {
          if (!disabled) {
            setIsOpen(!isOpen);
          }
        }}
        className={disabled ? 'opacity-50 cursor-not-allowed' : ''}
      >
        {trigger}
      </div>
      {isOpen && (
        <div className={`absolute right-0 mt-2 w-56 origin-top-right divide-y divide-gray-100 rounded-lg bg-white shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none z-50 ${menuClassName}`}>
          <div className="py-1">
            {items.map((item, index) => (
              <button
                key={index}
                disabled={item.disabled}
                onClick={() => {
                  item.onClick();
                  setIsOpen(false);
                }}
                className={`
                  group flex w-full items-center px-4 py-3 text-sm transition-colors
                  ${item.disabled 
                    ? 'text-gray-400 cursor-not-allowed bg-gray-50' 
                    : 'text-gray-700 hover:bg-violet-50 hover:text-violet-700'
                  }
                  ${item.className || ''}
                `}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
