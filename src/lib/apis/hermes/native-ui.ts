import {
    JsonRpcGatewayClient, hermesRequest, hermesWebSocketUrl,
    type GatewayEvent, type ServerRequest, type SessionResumeResult,
    type SessionLiveInfo, type TranscriptMessage,
} from './index';
import { durableSessionId } from './session';
import { transcriptRows } from './transcript';

export interface NativeUiUpdate {
    text: string; reasoning: string; tools: string; running: boolean; error: string;
}
export interface NativeUiCallbacks {
    update: (value: NativeUiUpdate) => void;
    connected?: (value: boolean) => void;
    requests: (value: ServerRequest[]) => void;
    identity: (stored: string, info: SessionLiveInfo) => void | Promise<void>;
    restore: (result: SessionResumeResult) => void;
}
export interface NativeAttachment {
    id?: string; url?: string; name?: string; type?: string; content_type?: string;
}
const escapeHtml = (value: string) => value.replace(/[&<>"]/g, (c) => (({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'} as Record<string,string>)[c]!));
const toolDetail = (name: string, content: string) =>
    '\n\n<details>\n<summary>' + escapeHtml(name) + '</summary>\n\n' + escapeHtml(content) + '\n</details>\n\n';
export function nativeUiContent(update: NativeUiUpdate): string {
    return (update.reasoning ? '<details type="reasoning" done="' + !update.running + '">\n<summary>Thinking</summary>\n\n' +
        escapeHtml(update.reasoning) + '\n</details>\n\n' : '') + update.tools + update.text;
}
/** Presentation only. This projection is never submitted as a model prompt. */
export function nativeUiHistory(messages: TranscriptMessage[]) {
    const history: { messages: Record<string, any>; currentId: string | null } = { messages: {}, currentId: null };
    for (const row of transcriptRows(messages)) {
        if (row.role === 'tool') {
            const target = history.currentId ? history.messages[history.currentId] : null;
            if (target?.role === 'assistant') target.content += toolDetail(row.name || 'Tool', row.text);
            continue;
        }
        const id = row.id;
        const message = {
            id, parentId: history.currentId, childrenIds: [] as string[], role: row.role,
            content: nativeUiContent({ text: row.text, reasoning: row.reasoning || '', tools: '', running: false, error: '' }),
            done: true, model: 'hermes-agent', modelName: 'Hermes', modelIdx: 0,
            models: row.role === 'user' ? ['hermes-agent'] : undefined,
            timestamp: messages.find((m) => 'history-' + m.row_id === row.id)?.timestamp || Math.floor(Date.now() / 1000),
        };
        if (history.currentId) history.messages[history.currentId].childrenIds.push(id);
        history.messages[id] = message;
        history.currentId = id;
    }
    return history;
}

/** Original OWUI components render native Hermes frames; no OWUI AI middleware. */
export class NativeUiBridge {
    readonly client = new JsonRpcGatewayClient({ requestIdPrefix: 'owui-native-', connectErrorMessage: 'Nie można połączyć z Hermesem' });
    private connecting: Promise<void> | null = null;
    private active = '';
    private stored = '';
    private disposed = false;
    private timer: ReturnType<typeof setTimeout> | undefined;
    private attempts = 0;
    private userCount = 0;
    private pending: ServerRequest[] = [];
    private value: NativeUiUpdate = { text: '', reasoning: '', tools: '', running: false, error: '' };
    constructor(private callbacks: NativeUiCallbacks) {
        this.client.onRequest((request) => {
            if (!['approval', 'clarify', 'sudo', 'secret', 'display.install.sudo'].includes(request.method)) return false;
            this.pending = [...this.pending.filter((r) => r.id !== request.id), request];
            this.callbacks.requests(this.pending);
            return true;
        });
        this.client.onAny((event) => this.event(event));
        this.client.onState((state) => {
            this.callbacks.connected?.(state === 'open');
            if (!this.disposed && this.stored && (state === 'closed' || state === 'error')) {
                clearTimeout(this.timer);
                this.timer = setTimeout(() => {
                    this.active = '';
                    void this.resume(this.stored).catch(() => {});
                }, Math.min(30000, 1000 * 2 ** Math.min(this.attempts++, 5)));
            }
        });
    }
    private publish() { this.callbacks.update({ ...this.value }); }
    private event(frame: GatewayEvent) {
        const event = frame as { type: string; session_id?: string; payload?: any };
        const data = event.payload || {};
        if (event.type === 'request.cancel') { this.answered(data.id); return; }
        if (event.session_id !== this.active) return;
        if (event.type === 'session.info') {
            this.stored = durableSessionId({ info: data }, this.stored);
            this.callbacks.identity(this.stored, data);
            return;
        } else if (event.type === 'message.start') {
            this.value.running = true;
        } else if (event.type === 'message.delta') {
            this.value.text += data.text || '';
        } else if (event.type === 'thinking.delta' || event.type === 'reasoning.delta') {
            this.value.reasoning += data.text || '';
        } else if (event.type === 'reasoning.available') {
            this.value.reasoning = data.text || '';
        } else if (event.type === 'message.interim') {
            if (!data.already_streamed) this.value.text += data.text || '';
        } else if (event.type === 'tool.complete') {
            this.value.tools += toolDetail(data.name || 'Tool', data.result_text || data.summary || '');
        } else if (event.type === 'message.complete') {
            if (typeof data.text === 'string' && data.text) this.value.text = data.text;
            if (typeof data.reasoning === 'string' && data.reasoning) this.value.reasoning = data.reasoning;
            this.value.running = false;
            this.value.error = data.error || data.failure_reason || '';
        } else if (event.type === 'error') {
            this.value.error = data.message || 'Błąd Hermesa';
            this.value.running = false;
        } else {
            // Metadata/usage/status events must not replace a restored response.
            return;
        }
        this.publish();
    }
    private async connect() {
        if (this.disposed) throw new Error('Połączenie jest zamknięte');
        if (this.client.connectionState === 'open') return;
        if (!this.connecting) this.connecting = this.client.connect(hermesWebSocketUrl(window.location))
            .then(() => { this.attempts = 0; }).finally(() => { this.connecting = null; });
        await this.connecting;
    }
    async resume(stored: string): Promise<SessionResumeResult> {
        this.stored = stored;
        await this.connect();
        await this.client.sessionReplayBarrier(this.active || stored);
        const result = await hermesRequest(this.client, 'session.resume', { session_id: stored, close_on_disconnect: false });
        this.active = result.session_id;
        this.stored = durableSessionId(result, stored);
        this.userCount = result.messages.filter((m) => m.role === 'user' && m.display_kind !== 'hidden').length;
        this.value = { text: result.inflight?.assistant || '', reasoning: '', tools: '', running: !!result.running, error: '' };
        await this.callbacks.identity(this.stored, result.info);
        this.callbacks.restore(result);
        return result;
    }
    async send(text: string, stored: string, attachments: NativeAttachment[], userOrdinal: number) {
        await this.connect();
        if (stored && (this.stored !== stored || !this.active)) await this.resume(stored);
        if (!this.active) {
            if (userOrdinal > 0) throw new Error('Ta rozmowa nie jest przypisana do sesji Hermesa. Otwórz jej oryginał z listy Hermesa.');
            const result = await hermesRequest(this.client, 'session.create', { source: 'web', close_on_disconnect: false });
            this.active = result.session_id;
            this.stored = durableSessionId(result);
            await this.callbacks.identity(this.stored, result.info);
        }
        if (userOrdinal < this.userCount) throw new Error('Edycja wcześniejszych wiadomości i regeneracja wymagają natywnego rozgałęzienia Hermesa. Ten adapter nie zmienia jego historii.');
        for (const file of attachments) await this.attach(file);
        this.value = { text: '', reasoning: '', tools: '', running: true, error: '' };
        this.publish();
        // Exact user text; no system, memory, history, parameters, tools or filters.
        const result = await hermesRequest(this.client, 'prompt.submit', { session_id: this.active, text });
        this.userCount++;
        if (result.voice_stopped) { this.value.running = false; this.publish(); }
    }
    private async attach(file: NativeAttachment) {
        let url = file.id ? '/api/v1/files/' + encodeURIComponent(file.id) + '/content' : file.url;
        if (!url) throw new Error('Ten typ załącznika nie jest plikiem. Zapisz go jako plik i dołącz do wiadomości.');
        if (!url.startsWith('data:')) {
            const parsed = new URL(url, window.location.origin);
            if (parsed.origin !== window.location.origin) throw new Error('Zewnętrzne załączniki nie są pobierane automatycznie');
        }
        const response = await fetch(url, { credentials: 'same-origin', headers: url.startsWith('data:') ? {} : { Authorization: 'Bearer ' + localStorage.token } });
        if (!response.ok) throw new Error('Nie można odczytać załącznika');
        const blob = await response.blob();
        if (blob.size > 10 * 1024 * 1024) throw new Error('Załącznik przekracza 10 MiB limitu transportu Hermesa');
        const dataUrl = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result));
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
        const bytes = dataUrl.slice(dataUrl.indexOf(',') + 1);
        const name = file.name || 'attachment';
        if ((file.content_type || blob.type).startsWith('image/') || file.type === 'image') {
            await hermesRequest(this.client, 'image.attach_bytes', { session_id: this.active, content_base64: bytes, filename: name });
        } else if ((file.content_type || blob.type) === 'application/pdf' || name.toLowerCase().endsWith('.pdf')) {
            await hermesRequest(this.client, 'pdf.attach', { session_id: this.active, content_base64: bytes, filename: name });
        } else {
            await hermesRequest(this.client, 'file.attach', { session_id: this.active, data_url: dataUrl, name });
        }
    }
    answered(id: string) { this.pending = this.pending.filter((r) => r.id !== id); this.callbacks.requests(this.pending); }
    async interrupt() { if (this.active) await hermesRequest(this.client, 'session.interrupt', { session_id: this.active }); }
    close() { this.disposed = true; clearTimeout(this.timer); this.client.close(); }
}
