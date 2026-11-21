import type { AgentReviewItem } from '@/shared/api';
import { paths } from '@/shared/config';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { agentReviewApi } from './api';

export function useReviewActions(it: AgentReviewItem, defaultAuthor: string) {
  const navigate = useNavigate();
  const [author, setAuthor] = useState(defaultAuthor);
  const [comment, setComment] = useState('');
  const [retry, setRetry] = useState(false);
  const [push, setPush] = useState(false);
  const cache = useQueryClient();
  const [msg, setMsg] = useState('');
  const mutation = useMutation({
    mutationFn: async (action: 'approve' | 'reject' | 'reset' | 'apply' | 'remove') => {
      if (action === 'apply') {
        const data = await agentReviewApi.apply(it.issue_id, push);
        return [data.result, data.status].join(' → ') + (data.pr_url ? ' · ' + data.pr_url : '');
      }
      if (action === 'remove') await agentReviewApi.remove(it.issue_id);
      else if (action === 'reset') await agentReviewApi.reset(it.issue_id);
      else await agentReviewApi.decide(it.issue_id, { decision: action, author, comment, retry });
      return '';
    },
    onMutate: () => setMsg('выполняется…'),
    onError: (error) => setMsg(error.message),
    onSuccess: async (message, action) => {
      setMsg(message);
      if (action === 'reset') navigate(paths.agentReview + '?status=proposed');
      await cache.invalidateQueries({ queryKey: ['agent-review'] });
    },
  });
  const busy = mutation.isPending;
  const removing = busy && mutation.variables === 'remove';
  const resetting = busy && mutation.variables === 'reset';
  const decide = (decision: 'approve' | 'reject') => mutation.mutate(decision);
  const apply = () => mutation.mutate('apply');
  const reset = () => mutation.mutate('reset');

  return {
    author,
    setAuthor,
    comment,
    setComment,
    retry,
    setRetry,
    push,
    setPush,
    mutation,
    busy,
    removing,
    resetting,
    decide,
    apply,
    reset,
    msg,
  };
}
