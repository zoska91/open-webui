<script lang="ts">
	import { onMount, onDestroy, tick } from 'svelte';
	import {
		JsonRpcGatewayClient,
		hermesRequest,
		hermesWebSocketUrl,
		type ConnectionState,
		type GatewayEvent,
		type ServerRequest,
		type SessionListRow,
		type SessionLiveInfo,
		type SessionResumeResult
	} from '$lib/apis/hermes';
	import { transcriptRows, type ChatRow } from '$lib/apis/hermes/transcript';
	import { durableSessionId } from '$lib/apis/hermes/session';
	import type { GatewayEventName } from '$lib/apis/hermes/native/gateway-events';
	import Markdown from '$lib/components/chat/Messages/Markdown.svelte';
	import RequestCard from './RequestCard.svelte';

	const storageKey = 'hermes.application.last-session';
	let client: JsonRpcGatewayClient;
	let connection: ConnectionState = 'idle';
	let ready = false;
	let sessions: SessionListRow[] = [];
	let activeId = '';
	let storedId = '';
	let info: SessionLiveInfo = {};
	let rows: ChatRow[] = [];
	let requests: ServerRequest[] = [];
	let input = '';
	let error = '';
	let status = '';
	let drawer = false;
	let loading = false;
	let submitting = false;
	let running = false;
	let streamingId = '';
	let listFilter = '';
	let transcript: HTMLDivElement;
	let followBottom = true;
	let reconnectTimer: ReturnType<typeof setTimeout>;
	let reconnectAttempts = 0;
	let destroyed = false;
	let loadGeneration = 0;
	let rowSequence = 0;
	let epoch = '';
	const cleanups: (() => void)[] = [];

	$: filteredSessions = sessions.filter((session) =>
		`${session.title ?? ''} ${session.preview ?? ''}`
			.toLocaleLowerCase()
			.includes(listFilter.toLocaleLowerCase())
	);
	$: activeRequests = requests.filter(
		(request) =>
			!request.params.session_id ||
			request.params.session_id === activeId ||
			request.params.session_id === storedId
	);
	$: otherRequest = requests.find(
		(request) =>
			request.params.session_id &&
			request.params.session_id !== activeId &&
			request.params.session_id !== storedId
	);
	$: activeTitle =
		info.title || sessions.find((session) => session.id === storedId)?.title || 'Nowa rozmowa';
	$: connectionLabel = ready
		? 'Połączono'
		: connection === 'connecting' || connection === 'open'
			? 'Łączenie…'
			: 'Brak połączenia';
	$: if (rows || activeRequests) scrollToBottom();

	function nextRowId() {
		return `live-${++rowSequence}`;
	}
	function rememberSession() {
		if (storedId) localStorage.setItem(storageKey, storedId);
		else localStorage.removeItem(storageKey);
	}
	async function scrollToBottom(force = false) {
		await tick();
		if (transcript && (followBottom || force)) transcript.scrollTop = transcript.scrollHeight;
	}
	function scrollHandler() {
		followBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 100;
	}
	function requestAnswered(id: string) {
		requests = requests.filter((request) => request.id !== id);
	}
	function receiveRequest(request: ServerRequest) {
		if (!['approval', 'clarify', 'sudo', 'secret', 'display.install.sudo'].includes(request.method))
			return false;
		// Replace the callback when the same open request arrives on the new socket.
		requests = [...requests.filter((item) => item.id !== request.id), request];
		return true;
	}
	async function refreshSessions() {
		const result = await hermesRequest(client, 'session.list', { limit: 200 });
		sessions = result.sessions;
	}
	function applyResume(result: SessionResumeResult, requestedId: string) {
		activeId = result.session_id;
		storedId = durableSessionId(result, requestedId);
		info = result.info;
		running = !!(result.running ?? result.info.running);
		if (Array.isArray(result.open_requests)) {
			const openIds = new Set(result.open_requests.map((request) => request.id));
			requests = requests.filter(
				(request) =>
					(request.params.session_id !== activeId && request.params.session_id !== storedId) ||
					openIds.has(request.id)
			);
		}
		rows = transcriptRows(result.messages);
		streamingId = '';
		if (result.inflight) {
			const { user, assistant } = result.inflight;
			if (user && rows.filter((row) => row.role === 'user').at(-1)?.text !== user)
				rows = [...rows, { id: nextRowId(), role: 'user', text: user }];
			if (assistant) {
				streamingId = nextRowId();
				rows = [...rows, { id: streamingId, role: 'assistant', text: assistant }];
			}
		}
		rememberSession();
	}
	async function selectSession(id: string) {
		const replaySession = activeId || id;
		const generation = ++loadGeneration;
		loading = true;
		error = '';
		status = '';
		drawer = false;
		activeId = id;
		storedId = id;
		rows = [];
		info = {};
		streamingId = '';
		followBottom = true;
		try {
			// Complete reconnect replay before taking the authoritative native snapshot.
			await client.sessionReplayBarrier(replaySession);
			if (generation !== loadGeneration || destroyed || client.connectionState !== 'open') return;
			const result = await hermesRequest(client, 'session.resume', {
				session_id: id,
				close_on_disconnect: false
			});
			if (generation !== loadGeneration || destroyed) return;
			applyResume(result, id);
		} catch (cause) {
			if (generation === loadGeneration)
				error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			if (generation === loadGeneration) loading = false;
		}
	}
	function newSession() {
		loadGeneration++;
		activeId = '';
		storedId = '';
		info = {};
		rows = [];
		streamingId = '';
		loading = false;
		running = false;
		error = '';
		status = '';
		drawer = false;
		rememberSession();
		// A new Hermes session is created only when the user sends a message.
	}
	async function restoreConnection() {
		try {
			await refreshSessions();
			if (destroyed || client.connectionState !== 'open') return;
			const id = storedId || localStorage.getItem(storageKey);
			if (id) await selectSession(id);
			if (destroyed || client.connectionState !== 'open') return;
			ready = true;
			reconnectAttempts = 0;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
		}
	}
	async function connect() {
		if (destroyed) return;
		clearTimeout(reconnectTimer);
		try {
			await client.connect(hermesWebSocketUrl(window.location));
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
			scheduleReconnect();
		}
	}
	function scheduleReconnect() {
		if (destroyed) return;
		clearTimeout(reconnectTimer);
		const delay = Math.min(30_000, 1_000 * 2 ** Math.min(reconnectAttempts++, 5));
		reconnectTimer = setTimeout(connect, delay);
	}
	async function readHistory(id: string) {
		const generation = loadGeneration;
		try {
			const result = await hermesRequest(client, 'session.history', { session_id: id });
			if (generation !== loadGeneration || id !== activeId || running || destroyed) return;
			rows = transcriptRows(result.messages);
			streamingId = '';
		} catch {
			/* A disconnected client recovers through resume and native replay. */
		}
	}
	function assistantRow() {
		if (!streamingId || !rows.some((row) => row.id === streamingId)) {
			streamingId = nextRowId();
			rows = [...rows, { id: streamingId, role: 'assistant', text: '' }];
		}
		return streamingId;
	}
	function updateAssistant(update: (row: ChatRow) => ChatRow) {
		const id = assistantRow();
		rows = rows.map((row) => (row.id === id ? update(row) : row));
	}
	function receiveEvent(frame: GatewayEvent) {
		const event = frame as { [K in GatewayEventName]: GatewayEvent<K> }[GatewayEventName];
		if (event.type === 'gateway.ready') {
			const nextEpoch = event.payload?.replay_epoch;
			if (epoch && nextEpoch && epoch !== nextEpoch) requests = [];
			epoch = nextEpoch || '';
			return;
		}
		if (event.type === 'sessions.changed' || event.type === 'session.title') {
			void refreshSessions().catch(() => {});
		}
		if (event.type === 'request.cancel') {
			requestAnswered(event.payload!.id);
			return;
		}
		if (!event.session_id || event.session_id !== activeId) return;
		switch (event.type) {
			case 'session.info':
				info = { ...info, ...event.payload };
				running = !!info.running;
				storedId = durableSessionId({ info }, storedId);
				rememberSession();
				break;
			case 'message.start':
				running = true;
				streamingId = '';
				status = '';
				break;
			case 'message.delta':
				updateAssistant((row) => ({ ...row, text: row.text + event.payload!.text }));
				break;
			case 'reasoning.delta':
			case 'thinking.delta':
				updateAssistant((row) => ({
					...row,
					reasoning: (row.reasoning ?? '') + event.payload!.text
				}));
				break;
			case 'reasoning.available':
				updateAssistant((row) => ({ ...row, reasoning: event.payload!.text }));
				break;
			case 'message.interim':
				if (!event.payload!.already_streamed)
					updateAssistant((row) => ({ ...row, text: event.payload!.text }));
				streamingId = '';
				break;
			case 'message.complete': {
				const payload = event.payload!;
				if (typeof payload.text === 'string' && payload.text)
					updateAssistant((row) => ({ ...row, text: payload.text as string }));
				running = false;
				status = '';
				error = payload.error || payload.failure_reason || '';
				streamingId = '';
				void readHistory(activeId);
				void refreshSessions().catch(() => {});
				break;
			}
			case 'tool.generating':
				status = `Przygotowuje: ${event.payload!.name}`;
				break;
			case 'tool.start': {
				const payload = event.payload!;
				rows = [
					...rows.filter((row) => row.id !== payload.tool_id),
					{
						id: payload.tool_id,
						role: 'tool',
						text: payload.context || '',
						name: payload.name,
						args: payload.args,
						status: 'running'
					}
				];
				status = '';
				break;
			}
			case 'tool.complete': {
				const payload = event.payload!;
				const tool: ChatRow = {
					id: payload.tool_id,
					role: 'tool',
					name: payload.name,
					args: payload.args,
					text: payload.result_text || '',
					summary: payload.summary || undefined,
					status: 'complete'
				};
				rows = rows.some((row) => row.id === tool.id)
					? rows.map((row) => (row.id === tool.id ? tool : row))
					: [...rows, tool];
				break;
			}
			case 'status.update':
				status = event.payload!.text;
				break;
			case 'notice':
				status = event.payload!.message;
				break;
			case 'error':
				error = event.payload!.message;
				running = false;
				break;
			case 'session.reclaimed':
				ready = false;
				status = 'Sesja została zamknięta przez Hermesa. Połącz ponownie.';
				break;
		}
	}
	async function send() {
		const text = input.trim();
		if (!text || !ready || submitting || loading || running) return;
		submitting = true;
		error = '';
		try {
			if (!activeId) {
				const result = await hermesRequest(client, 'session.create', {
					source: 'web',
					close_on_disconnect: false
				});
				activeId = result.session_id;
				storedId = durableSessionId(result);
				info = result.info;
				rememberSession();
			}
			rows = [...rows, { id: nextRowId(), role: 'user', text }];
			input = '';
			followBottom = true;
			running = true;
			streamingId = '';
			// Hermes receives the user's words only. No history replay, system prompt or UI tools.
			const result = await hermesRequest(client, 'prompt.submit', { session_id: activeId, text });
			if (result.voice_stopped) {
				running = false;
				void readHistory(activeId);
			}
		} catch (cause) {
			const failure = `${cause instanceof Error ? cause.message : String(cause)}. Wiadomość nie zostanie wysłana ponownie automatycznie.`;
			// On an ambiguous socket failure the next resume is authoritative.
			if (client.connectionState === 'open' && activeId) await selectSession(storedId || activeId);
			error = failure;
		} finally {
			submitting = false;
		}
	}
	async function interrupt() {
		if (!ready || !activeId) return;
		try {
			await hermesRequest(client, 'session.interrupt', { session_id: activeId });
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
		}
	}
	function inputKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
			event.preventDefault();
			void send();
		}
	}
	onMount(() => {
		client = new JsonRpcGatewayClient({
			requestIdPrefix: 'owui-',
			connectErrorMessage: 'Nie można połączyć z Hermesem'
		});
		cleanups.push(
			client.onRequest(receiveRequest),
			client.onAny(receiveEvent),
			client.onState((state) => {
				connection = state;
				if (state === 'open') void restoreConnection();
				else {
					ready = false;
					if (state === 'closed' || state === 'error') scheduleReconnect();
				}
			})
		);
		void connect();
		const wake = () => {
			if (document.visibilityState === 'visible' && client.connectionState !== 'open')
				void connect();
		};
		window.addEventListener('online', connect);
		document.addEventListener('visibilitychange', wake);
		cleanups.push(
			() => window.removeEventListener('online', connect),
			() => document.removeEventListener('visibilitychange', wake)
		);
	});
	onDestroy(() => {
		destroyed = true;
		clearTimeout(reconnectTimer);
		cleanups.forEach((cleanup) => cleanup());
		client?.close();
	});
</script>

<div class="flex h-full min-h-0 w-full bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100">
	{#if drawer}
		<button
			class="fixed inset-0 z-30 bg-black/40 md:hidden"
			aria-label="Zamknij listę rozmów"
			on:click={() => (drawer = false)}
		></button>
	{/if}
	<aside
		class:hidden={!drawer}
		class="absolute inset-y-0 left-0 z-40 flex w-72 shrink-0 flex-col border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 md:static md:!flex md:w-64 xl:w-72"
	>
		<div class="p-4">
			<div class="flex items-center justify-between mb-4">
				<span class="font-semibold">Rozmowy</span><button
					class="md:hidden rounded-lg px-2 py-1"
					aria-label="Zamknij listę rozmów"
					on:click={() => (drawer = false)}>✕</button
				>
			</div>
			<button
				disabled={!ready || submitting}
				on:click={newSession}
				class="w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2.5 text-sm font-medium hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-40"
				>＋ Nowa rozmowa</button
			>
			<input
				type="search"
				bind:value={listFilter}
				placeholder="Szukaj rozmowy"
				aria-label="Szukaj rozmowy"
				class="mt-3 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-transparent px-3 py-2 text-sm"
			/>
		</div>
		<div class="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
			{#each filteredSessions as session (session.id)}
				<button
					disabled={!ready || submitting}
					on:click={() => selectSession(session.id)}
					class="mb-1 w-full rounded-xl p-3 text-left text-sm hover:bg-gray-200/60 dark:hover:bg-gray-800 disabled:opacity-40 {session.id ===
					storedId
						? 'bg-gray-200 dark:bg-gray-800'
						: ''}"
				>
					<div class="truncate font-medium">
						{session.title || session.preview || 'Rozmowa bez tytułu'}
					</div>
					<div class="mt-1 truncate text-xs text-gray-500">
						{session.source || 'Hermes'} · {session.message_count ?? 0} wiadomości
					</div>
				</button>
			{/each}
			{#if ready && !filteredSessions.length}<p class="px-3 text-sm text-gray-500">
					Brak rozmów.
				</p>{/if}
		</div>
	</aside>
	<main class="flex min-w-0 flex-1 flex-col">
		<header
			class="flex shrink-0 items-center gap-3 border-b border-gray-200 dark:border-gray-800 px-4 py-3 sm:px-6"
		>
			<button
				class="md:hidden rounded-lg px-2 py-1 text-xl"
				aria-label="Pokaż rozmowy"
				on:click={() => (drawer = true)}>☰</button
			>
			<div class="min-w-0 flex-1">
				<h1 class="truncate text-sm font-semibold sm:text-base">{activeTitle}</h1>
				<p class="mt-0.5 truncate text-xs text-gray-500">
					Hermes{info.model ? ` · ${info.model}` : ''}
				</p>
			</div>
			<span class="flex items-center gap-1.5 text-xs text-gray-500"
				><span class="h-2 w-2 rounded-full" class:bg-emerald-500={ready} class:bg-amber-500={!ready}
				></span><span class="hidden sm:inline">{connectionLabel}</span></span
			>
			{#if !ready}<button
					on:click={connect}
					class="rounded-lg border border-gray-300 dark:border-gray-700 px-2 py-1 text-xs"
					>Połącz</button
				>{/if}
		</header>
		{#if otherRequest}
			<button
				disabled={!ready}
				on:click={() => selectSession(otherRequest!.params.session_id!)}
				class="border-b border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950/20 px-4 py-2 text-left text-xs text-amber-800 dark:text-amber-200 disabled:opacity-40"
				>Inna rozmowa wymaga Twojej odpowiedzi. Otwórz ją →</button
			>
		{/if}
		<div
			bind:this={transcript}
			on:scroll={scrollHandler}
			class="min-h-0 flex-1 overflow-y-auto overscroll-contain"
		>
			<div class="mx-auto w-full max-w-3xl space-y-5 px-4 py-6 sm:px-6">
				{#if loading}<p class="py-10 text-center text-sm text-gray-500">Otwieranie rozmowy…</p>
				{:else if !rows.length}
					<div class="py-12 sm:py-24 text-center">
						<div
							class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gray-100 dark:bg-gray-800 text-xl"
						>
							✦
						</div>
						<h2 class="text-xl font-semibold">Porozmawiaj z Hermesem</h2>
						<p class="mt-2 text-sm text-gray-500">
							Twoje rozmowy, narzędzia i pamięć są w Hermesie.
						</p>
					</div>
				{/if}
				{#each rows as row (row.id)}
					{#if row.role === 'tool'}
						<details
							class="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 px-4 py-3"
						>
							<summary class="cursor-pointer text-sm"
								><span class="mr-2 text-gray-400">{row.status === 'running' ? '◌' : '✓'}</span><span
									class="font-medium">{row.name || 'Narzędzie'}</span
								>{#if row.summary}<span class="ml-2 text-gray-500">{row.summary}</span
									>{/if}</summary
							>
							{#if row.args}<pre
									class="mt-3 max-h-56 overflow-auto whitespace-pre-wrap break-all text-xs text-gray-500">{JSON.stringify(
										row.args,
										null,
										2
									)}</pre>{/if}
							{#if row.text}<pre
									class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-all text-xs">{row.text}</pre>{/if}
						</details>
					{:else}
						<article
							class="min-w-0"
							class:flex={row.role === 'user'}
							class:justify-end={row.role === 'user'}
						>
							<div
								class="min-w-0 max-w-full {row.role === 'user'
									? 'rounded-2xl bg-gray-100 dark:bg-gray-800 px-4 py-3'
									: ''}"
							>
								{#if row.role === 'assistant'}<div class="mb-2 text-xs font-medium text-gray-500">
										Hermes
									</div>{/if}
								{#if row.reasoning}<details class="mb-3 text-sm text-gray-500">
										<summary class="cursor-pointer">Rozumowanie</summary>
										<pre class="mt-2 whitespace-pre-wrap break-words text-xs">{row.reasoning}</pre>
									</details>{/if}
								{#if row.role === 'user'}<p
										class="whitespace-pre-wrap break-words text-sm sm:text-base"
									>
										{row.text}
									</p>
								{:else}<div
										class="prose dark:prose-invert max-w-none break-words text-sm sm:text-base"
									>
										<Markdown
											id={row.id}
											content={row.text}
											done={!running || row.id !== streamingId}
											editCodeBlock={false}
											allowEmbeds={false}
										/>
									</div>{/if}
							</div>
						</article>
					{/if}
				{/each}
				{#each activeRequests as request (request.id)}<RequestCard
						{request}
						connected={ready}
						onanswered={requestAnswered}
					/>{/each}
				{#if running}<div role="status" class="flex items-center gap-2 text-sm text-gray-500">
						<span class="animate-pulse">●</span>{status || 'Hermes pracuje…'}
					</div>{:else if status}<p role="status" class="text-sm text-gray-500">{status}</p>{/if}
			</div>
		</div>
		<footer class="shrink-0 px-4 pb-4 pt-2 sm:px-6">
			<div class="mx-auto max-w-3xl">
				{#if error}<div
						role="alert"
						class="mb-3 flex items-start gap-3 rounded-xl bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-700 dark:text-red-300"
					>
						<span class="min-w-0 flex-1 break-words">{error}</span><button
							aria-label="Ukryj błąd"
							on:click={() => (error = '')}>✕</button
						>
					</div>{/if}
				<form
					on:submit|preventDefault={send}
					class="flex items-end gap-2 rounded-2xl border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-2 shadow-sm"
				>
					<textarea
						bind:value={input}
						on:keydown={inputKeydown}
						rows="2"
						placeholder={ready ? 'Napisz do Hermesa…' : 'Łączenie z Hermesem…'}
						aria-label="Wiadomość do Hermesa"
						disabled={!ready || loading || submitting}
						class="max-h-52 min-h-14 min-w-0 flex-1 resize-y bg-transparent px-2 py-2 text-sm outline-none sm:text-base disabled:opacity-50"
					></textarea>
					{#if running}<button
							type="button"
							on:click={interrupt}
							disabled={!ready}
							aria-label="Zatrzymaj odpowiedź"
							class="mb-1 rounded-xl bg-gray-900 dark:bg-gray-100 px-4 py-2 text-sm font-medium text-white dark:text-gray-900 disabled:opacity-40"
							>Stop</button
						>
					{:else}<button
							type="submit"
							disabled={!ready || !input.trim() || submitting || loading}
							aria-label="Wyślij wiadomość"
							class="mb-1 rounded-xl bg-gray-900 dark:bg-gray-100 px-4 py-2 text-sm font-medium text-white dark:text-gray-900 disabled:opacity-40"
							>Wyślij</button
						>{/if}
				</form>
			</div>
		</footer>
	</main>
</div>
