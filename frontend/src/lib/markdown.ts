// Простой рендер Markdown-отчёта ИИ-оценки — тот же, что фактически работал в athlete_profile.html
// (marked там не подключался, срабатывал этот запасной вариант), поэтому вид отчёта не меняется.
// Текст сначала экранируется, так что HTML из ответа модели в страницу не попадёт.

export function renderAssessmentMarkdown(md: string): string {
  const escaped = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escaped
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^#### (.*$)/gim, '<h4>$1</h4>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/^- (.*$)/gim, '<li>$1</li>')
    .replace(/\n\n/gim, '<p></p>')
    .replace(/\n/gim, '<br>');
}
