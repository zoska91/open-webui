import type { TranscriptMessage } from './native/gateway-contract.generated';

export interface ChatRow {
	id: string;
	role: 'user' | 'assistant' | 'tool';
	text: string;
	reasoning?: string;
	name?: string;
	args?: Record<string, unknown> | null;
	status?: 'running' | 'complete';
	summary?: string;
}

export function textContent(content: unknown): string {
	if (typeof content === 'string') return content;
	if (!Array.isArray(content)) return '';
	return content
		.map((part) => {
			if (!part || typeof part !== 'object') return '';
			return typeof part.text === 'string' ? part.text : '';
		})
		.filter(Boolean)
		.join('\n');
}

/** Hermes projects its durable history; the UI only renders visible rows. */
export function transcriptRows(messages: TranscriptMessage[]): ChatRow[] {
	return messages.flatMap((message, index) => {
		if (message.display_kind === 'hidden') return [];
		if (!['user', 'assistant', 'tool'].includes(message.role)) return [];
		const text = message.text ?? textContent(message.content);
		if (!text && !message.reasoning && message.role !== 'tool') return [];
		return [
			{
				id: message.tool_call_id ?? `history-${message.row_id ?? index}`,
				role: message.role as ChatRow['role'],
				text,
				reasoning: message.reasoning ?? undefined,
				name: message.name ?? undefined,
				args: message.args,
				status: 'complete' as const
			}
		];
	});
}

/** Native clarify accepts a JSON-encoded list for multiple selections. */
export function clarifyAnswer(selected: string[], other: string, multi: boolean): string {
	const values = [...selected, ...(other.trim() ? [other.trim()] : [])];
	return multi ? (values.length ? JSON.stringify(values) : '') : other.trim() || selected[0] || '';
}
