<script lang="ts">
	import type { ApprovalChoice, ClarifyQuestion, ServerRequest } from '$lib/apis/hermes';
	import { clarifyAnswer } from '$lib/apis/hermes/transcript';

	export let request: ServerRequest;
	export let connected = false;
	export let onanswered: (id: string) => void = () => {};

	let selected: Record<string, string[]> = {};
	let other: Record<string, string> = {};
	let secret = '';

	const labels: Record<ApprovalChoice, string> = {
		once: 'Zezwól raz',
		session: 'Zezwól w tej sesji',
		always: 'Zezwól zawsze',
		deny: 'Odrzuć'
	};
	$: choices = Array.isArray(request.params.choices)
		? request.params.choices.filter(
				(choice): choice is ApprovalChoice =>
					typeof choice === 'string' && Object.hasOwn(labels, choice)
			)
		: [];
	$: questions = (
		Array.isArray(request.params.questions) && request.params.questions.length
			? request.params.questions
			: [
					{
						qid: 'single',
						question: String(request.params.question ?? ''),
						choices: request.params.choices,
						multi_select: request.params.multi_select
					}
				]
	) as ClarifyQuestion[];
	$: locked = (request.params.answers ?? {}) as Record<string, string>;

	function answer(result: Record<string, unknown>) {
		if (!connected) return;
		request.respond(result);
		secret = '';
		onanswered(request.id);
	}

	function toggle(question: ClarifyQuestion, value: string) {
		const values = selected[question.qid] ?? [];
		selected = {
			...selected,
			[question.qid]: question.multi_select
				? values.includes(value)
					? values.filter((item) => item !== value)
					: [...values, value]
				: [value]
		};
		if (!question.multi_select) other = { ...other, [question.qid]: '' };
	}

	function submitClarify() {
		const answers = Object.fromEntries(
			questions.map((question) => [
				question.qid,
				locked[question.qid] ??
					clarifyAnswer(
						selected[question.qid] ?? [],
						other[question.qid] ?? '',
						!!question.multi_select
					)
			])
		);
		answer(
			Array.isArray(request.params.questions) && request.params.questions.length
				? { answers }
				: { answer: answers.single }
		);
	}
</script>

<section
	class="rounded-2xl border border-amber-300/60 dark:border-amber-800/80 bg-amber-50 dark:bg-amber-950/20 p-4 sm:p-5"
>
	{#if request.method === 'approval'}
		<h3 class="font-semibold text-gray-900 dark:text-gray-100">Hermes prosi o zgodę</h3>
		{#if request.params.description}<p class="mt-2 text-sm">
				{String(request.params.description)}
			</p>{/if}
		{#if request.params.command}
			<pre
				class="mt-3 max-h-56 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-white/70 dark:bg-black/20 p-3 text-xs">{String(
					request.params.command
				)}</pre>
		{/if}
		<div class="mt-4 flex flex-wrap gap-2">
			{#each choices as choice}
				<button
					disabled={!connected}
					on:click={() => answer({ choice })}
					class="rounded-xl border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm font-medium hover:bg-white dark:hover:bg-gray-800 disabled:opacity-40"
				>
					{labels[choice]}
				</button>
			{/each}
			{#if choices.length === 0}
				<p class="text-sm">Hermes nie przekazał dostępnych decyzji.</p>
			{/if}
		</div>
	{:else if request.method === 'clarify'}
		<form on:submit|preventDefault={submitClarify}>
			<h3 class="font-semibold">Hermes potrzebuje Twojej odpowiedzi</h3>
			{#each questions as question}
				<fieldset class="mt-4" disabled={!connected || Object.hasOwn(locked, question.qid)}>
					<legend class="mb-2 text-sm font-medium">{question.question}</legend>
					{#if Object.hasOwn(locked, question.qid)}
						<p class="text-sm text-gray-500">Odpowiedź: {locked[question.qid]}</p>
					{:else}
						<div class="flex flex-col gap-2">
							{#each question.choices ?? [] as choice}
								<label
									class="flex cursor-pointer items-start gap-2 rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-sm"
								>
									<input
										type={question.multi_select ? 'checkbox' : 'radio'}
										name={`${request.id}-${question.qid}`}
										checked={(selected[question.qid] ?? []).includes(choice)}
										on:change={() => toggle(question, choice)}
										class="mt-0.5"
									/>
									<span>{choice}</span>
								</label>
							{/each}
							<label class="text-xs text-gray-500 mt-1" for={`${request.id}-${question.qid}-other`}>
								{question.choices?.length ? 'Własna odpowiedź' : 'Odpowiedź'}
							</label>
							<textarea
								id={`${request.id}-${question.qid}-other`}
								rows="2"
								bind:value={other[question.qid]}
								on:input={() => {
									if (!question.multi_select) selected = { ...selected, [question.qid]: [] };
								}}
								class="w-full resize-y rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-3 text-sm"
							></textarea>
						</div>
					{/if}
				</fieldset>
			{/each}
			<div class="mt-4 flex gap-2">
				<button
					type="submit"
					disabled={!connected}
					class="rounded-xl bg-gray-900 dark:bg-gray-100 px-4 py-2 text-sm font-medium text-white dark:text-gray-900 disabled:opacity-40"
					>Wyślij odpowiedź</button
				>
				<button
					type="button"
					disabled={!connected}
					on:click={() => answer({})}
					class="rounded-xl px-3 py-2 text-sm hover:bg-white dark:hover:bg-gray-800 disabled:opacity-40"
					>Pomiń</button
				>
			</div>
		</form>
	{:else}
		<form on:submit|preventDefault={() => answer({ value: secret })}>
			<h3 class="font-semibold">
				{request.method === 'secret' ? 'Hermes prosi o sekret' : 'Hermes prosi o hasło sudo'}
			</h3>
			<p class="mt-2 text-sm">{String(request.params.prompt ?? request.params.command ?? '')}</p>
			<label class="mt-3 block text-xs text-gray-500" for={`${request.id}-secret`}>
				{request.method === 'secret' ? String(request.params.env_var ?? 'Wartość') : 'Hasło'}
			</label>
			<input
				id={`${request.id}-secret`}
				type="password"
				autocomplete="off"
				bind:value={secret}
				disabled={!connected}
				class="mt-1 w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-3 text-sm"
			/>
			<div class="mt-4 flex gap-2">
				<button
					type="submit"
					disabled={!connected || !secret}
					class="rounded-xl bg-gray-900 dark:bg-gray-100 px-4 py-2 text-sm font-medium text-white dark:text-gray-900 disabled:opacity-40"
					>Przekaż Hermesowi</button
				>
				<button
					type="button"
					disabled={!connected}
					on:click={() => answer({ value: '' })}
					class="rounded-xl px-3 py-2 text-sm hover:bg-white dark:hover:bg-gray-800 disabled:opacity-40"
					>Pomiń</button
				>
			</div>
		</form>
	{/if}
</section>
