import { client, responseData, type components } from '@/shared/api';

export type CollectionStartRequest = components['schemas']['BatchRequest'];
type CollectionApprovalRequest = components['schemas']['ApprovalRequest'];

export const collectionApi = {
  sources: (signal?: AbortSignal) => responseData(client.GET('/api/admin/collection/sources', { signal })),
  history: (signal?: AbortSignal) => responseData(client.GET('/api/admin/collection/batches', { signal })),
  batch: (batchId: number, signal?: AbortSignal) =>
    responseData(
      client.GET('/api/admin/collection/batches/{batch_id}', {
        params: { path: { batch_id: batchId } },
        signal,
      }),
    ),
  start: (body: CollectionStartRequest) =>
    responseData(client.POST('/api/admin/collection/batches', { body })),
  approve: (batchId: number, body: CollectionApprovalRequest) =>
    responseData(
      client.POST('/api/admin/collection/batches/{batch_id}/approve', {
        params: { path: { batch_id: batchId } },
        body,
      }),
    ),
};

export type CollectionSource = Awaited<ReturnType<typeof collectionApi.sources>>[number];
export type CollectionBatch = Awaited<ReturnType<typeof collectionApi.batch>>;
export type CollectionEvent = CollectionBatch['events'][number];
export type CollectionRace = CollectionEvent['races'][number];
export type CollectionProtocol = CollectionRace['protocols'][number];
