import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from './Icon';
import styles from './SelectField.module.css';

interface SelectFieldProps {
  label: string;
  name: string;
  options: readonly { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}

export function SelectField({ label, name, options, value, onChange }: SelectFieldProps) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const search = useRef({ prefix: '', time: 0 });
  const [highlight, setHighlight] = useState<number | null>(null);
  const open = highlight !== null && options.length > 0;
  const selected = options.findIndex((option) => option.value === value);
  const active = Math.min(highlight ?? 0, options.length - 1);
  const listId = `${id}-options`;

  useLayoutEffect(() => {
    const button = trigger.current;
    const popup = list.current;
    if (!open || !button || !popup) return;

    const position = () => {
      const field = button.getBoundingClientRect();
      const viewport = window.visualViewport;
      const top = (viewport?.offsetTop ?? 0) + 8;
      const left = (viewport?.offsetLeft ?? 0) + 8;
      const height = viewport?.height ?? document.documentElement.clientHeight;
      const width = viewport?.width ?? document.documentElement.clientWidth;
      const bottom = top + height - 16;
      if (field.bottom < top || field.top > bottom) {
        setHighlight(null);
        return;
      }
      const popupWidth = Math.min(Math.max(field.width, 176), width - 16);
      popup.style.width = `${popupWidth}px`;
      popup.style.left = `${Math.max(left, Math.min(field.left, left + width - 16 - popupWidth))}px`;
      const below = bottom - field.bottom - 4;
      const above = field.top - top - 4;
      const desired = Math.min(320, popup.scrollHeight + 2);
      const flip = below < desired && above > below;
      popup.style.maxHeight = `${Math.max(0, Math.min(320, flip ? above : below))}px`;
      popup.style.top = `${flip ? field.top - popup.offsetHeight - 4 : field.bottom + 4}px`;
    };

    position();
    const observer = new ResizeObserver(position);
    observer.observe(button);
    observer.observe(popup);
    window.addEventListener('scroll', position, true);
    window.addEventListener('resize', position);
    window.visualViewport?.addEventListener('resize', position);
    window.visualViewport?.addEventListener('scroll', position);
    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', position, true);
      window.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('scroll', position);
    };
  }, [open, options.length]);

  useLayoutEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: 'nearest' });
  }, [active, open]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: Event) => {
      const node = event.target;
      if (node instanceof Node && !trigger.current?.contains(node) && !list.current?.contains(node)) {
        setHighlight(null);
      }
    };
    document.addEventListener('pointerdown', closeOutside, true);
    document.addEventListener('focusin', closeOutside, true);
    return () => {
      document.removeEventListener('pointerdown', closeOutside, true);
      document.removeEventListener('focusin', closeOutside, true);
    };
  }, [open]);

  const choose = (index: number) => {
    const option = options[index];
    if (option) onChange(option.value);
    setHighlight(null);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowUp': {
        const next = active + (event.key === 'ArrowDown' ? 1 : -1);
        setHighlight(open ? Math.max(0, Math.min(next, options.length - 1)) : Math.max(0, selected));
        break;
      }
      case 'Home':
      case 'End':
        setHighlight(event.key === 'Home' ? 0 : options.length - 1);
        break;
      case 'Enter':
      case ' ':
        if (open) choose(active);
        else setHighlight(Math.max(0, selected));
        break;
      case 'Escape':
        if (!open) return;
        event.stopPropagation();
        setHighlight(null);
        break;
      case 'Tab':
        if (open) choose(active);
        return;
      default: {
        if (event.key.length !== 1) return;
        const char = event.key.toLocaleLowerCase();
        const now = Date.now();
        const prefix = now - search.current.time < 600 ? search.current.prefix + char : char;
        search.current = { time: now, prefix };
        const query = [...prefix].every((letter) => letter === char) ? char : prefix;
        const start = (open ? active : selected) + (query.length === 1 ? 1 : 0);
        for (let step = 0; step < options.length; step++) {
          const index = (Math.max(0, start) + step) % options.length;
          const option = options[index];
          if (option?.label.toLocaleLowerCase().startsWith(query)) {
            if (open) setHighlight(index);
            else onChange(option.value);
            break;
          }
        }
      }
    }
    event.preventDefault();
  };

  return (
    <div className="field">
      <label id={`${id}-label`} htmlFor={id}>
        {label}
      </label>
      <input type="hidden" name={name} value={value} />
      <button
        ref={trigger}
        id={id}
        type="button"
        role="combobox"
        className={`input input--sm ${styles.trigger}`}
        aria-labelledby={`${id}-label`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        disabled={options.length === 0}
        onKeyDown={onKeyDown}
        onClick={() => {
          trigger.current?.focus({ preventScroll: true });
          setHighlight(open ? null : Math.max(0, selected));
        }}
      >
        <span>{options[selected]?.label ?? value}</span>
        <Icon name="chevron" />
      </button>
      {open &&
        createPortal(
          <div ref={list} id={listId} role="listbox" aria-labelledby={`${id}-label`} className={styles.list}>
            {options.map((option, index) => (
              <button
                key={option.value}
                id={`${listId}-${index}`}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={index === selected}
                data-active={index === active || undefined}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  choose(index);
                  trigger.current?.focus({ preventScroll: true });
                }}
              >
                <span>{option.label}</span>
                {index === selected && <Icon name="check" className="icon-sm" />}
              </button>
            ))}
          </div>,
          trigger.current?.closest('dialog') ?? document.body,
        )}
    </div>
  );
}
