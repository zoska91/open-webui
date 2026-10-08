import type { SessionLiveInfo } from './native/gateway-contract.generated';

interface SessionIdentityResult {
	/** Live gateway address, deliberately excluded from durable candidates. */
	session_id?: string;
	stored_session_id?: string | null;
	session_key?: string | null;
	resumed?: string | null;
	info?: Pick<SessionLiveInfo, 'stored_session_id'>;
}

/**
 * Gateway session_id addresses a live runtime. Cold resume instead returns the
 * durable key in info/session_key/resumed; only that key survives a new socket.
 */
export function durableSessionId(result: SessionIdentityResult, requestedId = ''): string {
	const candidates = [
		result.stored_session_id,
		result.info?.stored_session_id,
		result.session_key,
		result.resumed,
		requestedId
	];
	return candidates.find((id): id is string => typeof id === 'string' && !!id.trim()) ?? '';
}
