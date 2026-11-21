// Переключатели внутри страницы (пол в рейтинге, дистанция, фильтры, поиск в протоколе) меняют адрес,
// но это та же страница — прокрутку сбрасывать не нужно. ScrollRestoration (AppLayout) прокручивает
// наверх только при переходе в другой раздел; для ссылок — проп preventScrollReset у <Link>.
export const KEEP_SCROLL = { preventScrollReset: true } as const;
