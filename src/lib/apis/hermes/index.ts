import { JsonRpcGatewayClient } from './native/json-rpc-gateway';
import type { RpcMethods } from './native/gateway-contract.generated';

export { JsonRpcGatewayClient };
export type { ConnectionState, GatewayEvent } from './native/json-rpc-gateway';
export type { ServerRequest } from './native/json-rpc-channel';
export type {
	ApprovalChoice,
	ClarifyQuestion,
	SessionListRow,
	SessionLiveInfo,
	SessionResumeResult,
	TranscriptMessage
} from './native/gateway-contract.generated';

/** Same-origin cookie authentication; upstream credentials never enter the browser. */
export function hermesWebSocketUrl(location: Pick<Location, 'protocol' | 'host'>): string {
	return `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/hermes/ws`;
}

/** Typed native RPC. This layer deliberately has no model, prompt or tool configuration. */
export function hermesRequest<M extends keyof RpcMethods>(
	client: JsonRpcGatewayClient,
	method: M,
	params: RpcMethods[M]['params']
): Promise<RpcMethods[M]['result']> {
	return client.request(method, params as Record<string, unknown>);
}
