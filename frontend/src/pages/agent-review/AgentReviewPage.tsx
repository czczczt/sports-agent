import { AgentReviewView } from '@/features/agent-review';
import { SITE_TITLE, useDocumentTitle } from '@/shared/hooks';

export function AgentReviewPage(): React.JSX.Element {
  useDocumentTitle(`Правки агента · ${SITE_TITLE}`);
  return <AgentReviewView />;
}
