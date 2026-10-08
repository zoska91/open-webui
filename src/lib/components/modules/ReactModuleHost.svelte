<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';
	import { createModuleRuntime } from '$lib/modules/runtime';
	import type { ApplicationModule } from '$lib/modules/types';

	export let module: ApplicationModule;

	let container: HTMLDivElement;
	let loading = true;
	let failed = false;
	let mounted = false;
	let generation = 0;
	let activeModule: ApplicationModule | undefined;
	let root: { unmount: () => void } | undefined;

	async function loadModule(nextModule: ApplicationModule) {
		const currentGeneration = ++generation;
		activeModule = nextModule;
		loading = true;
		failed = false;
		root?.unmount();
		root = undefined;

		try {
			const [adapter, implementation] = await Promise.all([
				import('$lib/modules/react-adapter'),
				nextModule.load()
			]);
			if (!mounted || currentGeneration !== generation) return;
			root = adapter.mountReactModule(
				container,
				nextModule.id,
				implementation.default,
				createModuleRuntime({
					moduleId: nextModule.id,
					userId: $user?.id ?? 'local',
					userName: $user?.name ?? '',
					navigate: goto
				}),
				() => {
					if (currentGeneration === generation) failed = true;
				}
			);
		} catch {
			if (currentGeneration === generation) failed = true;
		} finally {
			if (currentGeneration === generation) loading = false;
		}
	}

	$: if (mounted && module !== activeModule) void loadModule(module);

	onMount(() => {
		mounted = true;
		return () => {
			mounted = false;
			generation += 1;
			root?.unmount();
		};
	});
</script>

<div class="module-host min-w-0 w-full">
	{#if loading}
		<p role="status" class="p-6 text-sm text-gray-500">Ładowanie modułu…</p>
	{/if}
	{#if failed}
		<div role="alert" class="m-4 rounded-2xl border border-red-200 p-5 dark:border-red-900">
			<p class="font-medium">Nie udało się otworzyć modułu.</p>
			<button
				class="mt-3 rounded-lg border border-gray-200 px-4 py-2 text-sm dark:border-gray-700"
				on:click={() => loadModule(module)}>Spróbuj ponownie</button
			>
		</div>
	{/if}
	<div bind:this={container} hidden={loading || failed}></div>
</div>
