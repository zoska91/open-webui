import { afterEach, describe, expect, it, vi } from 'vitest';
import { JsonRpcRequestChannel } from './native/json-rpc-channel';
import { JsonRpcGatewayClient } from './native/json-rpc-gateway';
import { clarifyAnswer, transcriptRows } from './transcript';
import { hermesWebSocketUrl } from './index';
import { durableSessionId } from './session';

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('Hermes application transport', () => {
	it('uses the current origin without credentials in the URL', () => {
		expect(hermesWebSocketUrl({ protocol: 'https:', host: 'my-server:3000' })).toBe(
			'wss://my-server:3000/api/hermes/ws'
		);
	});

	it('never approves an unsupported server request', () => {
		const frames: Record<string, unknown>[] = [];
		const channel = new JsonRpcRequestChannel();
		channel.attach({ send: (text) => frames.push(JSON.parse(text)) });
		channel.handleFrame(
			JSON.stringify({ jsonrpc: '2.0', id: 'server-1', method: 'window.read', params: {} })
		);
		expect(frames).toEqual([
			{
				jsonrpc: '2.0',
				id: 'server-1',
				error: { code: -32601, message: 'no handler for server request: window.read' }
			}
		]);
		channel.detach(new Error('test finished'));
	});

	it('restores an unanswered approval and sends only the explicit decision', async () => {
		const frames: Record<string, unknown>[] = [];
		const channel = new JsonRpcRequestChannel();
		channel.attach({ send: (text) => frames.push(JSON.parse(text)) });
		let answer: ((result: Record<string, unknown>) => void) | undefined;
		channel.onRequest((request) => {
			expect(request.replayed).toBe(true);
			expect(request.params.choices).toEqual(['once', 'deny']);
			answer = request.respond;
		});
		const resume = channel.request('session.resume', { session_id: 'sid' });
		channel.handleFrame(
			JSON.stringify({
				id: frames[0].id,
				result: {
					open_requests: [
						{
							id: 'approve-1',
							method: 'approval',
							params: { session_id: 'sid', choices: ['once', 'deny'] }
						}
					]
				}
			})
		);
		await resume;
		expect(frames).toHaveLength(1);
		answer!({ choice: 'deny' });
		answer!({ choice: 'once' });
		expect(frames[1]).toEqual({ jsonrpc: '2.0', id: 'approve-1', result: { choice: 'deny' } });
		expect(frames).toHaveLength(2);
		channel.detach(new Error('test finished'));
	});

	it('orders replay before racing live frames and never resubmits a prompt', async () => {
		vi.stubGlobal('WebSocket', { OPEN: 1 });
		class Socket extends EventTarget {
			readyState = 0;
			frames: Record<string, unknown>[] = [];
			send(text: string) {
				this.frames.push(JSON.parse(text));
			}
			open() {
				this.readyState = 1;
				this.dispatchEvent(new Event('open'));
			}
			close() {
				this.readyState = 3;
				this.dispatchEvent(new Event('close'));
			}
			frame(data: unknown) {
				this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(data) }));
			}
		}
		const sockets: Socket[] = [];
		const client = new JsonRpcGatewayClient({
			socketFactory: () => {
				const socket = new Socket();
				sockets.push(socket);
				return socket as unknown as WebSocket;
			}
		});
		const seen: number[] = [];
		client.onAny((event) => {
			if (event.seq) seen.push(event.seq);
		});
		const first = client.connect('ws://example.test/api/hermes/ws');
		sockets[0].open();
		await first;
		sockets[0].frame({
			method: 'event',
			params: { type: 'message.delta', session_id: 'sid', seq: 1, payload: { text: 'a' } }
		});
		sockets[0].close();
		const second = client.connect('ws://example.test/api/hermes/ws');
		sockets[1].open();
		await second;
		expect(sockets[1].frames[0]).toMatchObject({
			method: 'session.events.since',
			params: { session_id: 'sid', last_seen: 1 }
		});
		sockets[1].frame({
			method: 'event',
			params: { type: 'message.delta', session_id: 'sid', seq: 3, payload: { text: 'c' } }
		});
		sockets[1].frame({
			id: sockets[1].frames[0].id,
			result: {
				epoch: 'same-process',
				events: [
					{ type: 'message.delta', session_id: 'sid', seq: 2, payload: { text: 'b' } },
					{ type: 'message.delta', session_id: 'sid', seq: 3, payload: { text: 'c' } }
				],
				open_requests: []
			}
		});
		await client.sessionReplayBarrier('sid');
		expect(seen).toEqual([1, 2, 3]);
		expect(
			sockets.flatMap((socket) => socket.frames).some((frame) => frame.method === 'prompt.submit')
		).toBe(false);
		client.close();
	});
});

describe('Hermes display projection', () => {
	it('keeps a durable cold-resume key across subsequent reloads', () => {
		// Actual _resume_response omits top-level stored_session_id.
		const cold = {
			session_id: 'runtime-new-socket',
			info: { stored_session_id: 'durable-history-key' },
			session_key: 'durable-history-key',
			resumed: 'durable-history-key'
		};
		const saved = durableSessionId(cold, 'durable-history-key');
		expect(saved).toBe('durable-history-key');
		expect(durableSessionId({ ...cold, session_id: 'runtime-next-socket' }, saved)).toBe(saved);
	});

	it('uses explicit create keys and native resume aliases without adopting runtime ids', () => {
		expect(durableSessionId({ stored_session_id: 'created-key', info: {} })).toBe('created-key');
		expect(durableSessionId({ session_key: 'native-key' }, 'requested-key')).toBe('native-key');
		expect(durableSessionId({ resumed: 'resolved-tip' }, 'old-key')).toBe('resolved-tip');
		expect(durableSessionId({ info: { stored_session_id: '' } }, 'requested-key')).toBe(
			'requested-key'
		);
		expect(durableSessionId({})).toBe('');
	});

	it('keeps visible user, assistant and tool rows without exposing system or hidden history', () => {
		expect(
			transcriptRows([
				{ role: 'system', text: 'internal' },
				{ role: 'user', text: 'hidden', display_kind: 'hidden' },
				{ role: 'user', row_id: 1, content: [{ type: 'text', text: 'Hello' }] },
				{ role: 'assistant', row_id: 2, text: 'World' },
				{ role: 'tool', tool_call_id: 'tool-1', name: 'read_file', text: 'file contents' }
			]).map(({ id, role, text }) => ({ id, role, text }))
		).toEqual([
			{ id: 'history-1', role: 'user', text: 'Hello' },
			{ id: 'history-2', role: 'assistant', text: 'World' },
			{ id: 'tool-1', role: 'tool', text: 'file contents' }
		]);
	});

	it('preserves choices with commas when sending multiple clarification answers', () => {
		expect(clarifyAnswer(['One, two', 'Three'], 'Custom', true)).toBe(
			'["One, two","Three","Custom"]'
		);
		expect(clarifyAnswer(['Choice'], ' own words ', false)).toBe('own words');
		expect(clarifyAnswer([], '', true)).toBe('');
	});
});
