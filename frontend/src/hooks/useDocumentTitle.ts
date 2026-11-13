import { useEffect } from 'react';

export const SITE_TITLE = 'Рейтинг спортсменов';

/** Заголовок вкладки. undefined — пока данные не загружены, оставляем прежний. */
export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    if (title) document.title = title;
  }, [title]);
}
