<script lang="ts">
	import { page } from '$app/stores';
	import { WEBUI_NAME, config, mobile, showSidebar } from '$lib/stores';
	import { getApplicationModule } from '$lib/modules/registry';
	import ReactModuleHost from '$lib/components/modules/ReactModuleHost.svelte';
	import SidebarIcon from '$lib/components/icons/Sidebar.svelte';

	$: module = getApplicationModule($page.params.moduleId);
	$: hermesOnly = $config?.features?.hermes_only === true;
</script>

<svelte:head>
	<!-- Preserve the upstream Open WebUI identifier required by LICENSE. -->
	<title>{module?.title ?? 'Moduł'} / {$WEBUI_NAME}</title>
</svelte:head>

<div
	class="flex min-w-0 min-h-0 w-full h-full max-h-full flex-col {$showSidebar && !hermesOnly
		? 'md:max-w-[calc(100%-var(--sidebar-width))]'
		: ''}"
>
	<nav class="flex shrink-0 items-center gap-2 px-3 py-2" aria-label="Nawigacja modułu">
		{#if !hermesOnly && ($mobile || !$showSidebar)}
			<button
				id="sidebar-toggle-button"
				class="rounded-lg p-2 hover:bg-gray-100 dark:hover:bg-gray-850"
				aria-label={$showSidebar ? 'Zamknij menu' : 'Otwórz menu'}
				on:click={() => showSidebar.set(!$showSidebar)}
			>
				<SidebarIcon className="size-4" />
			</button>
		{/if}
		<span class="text-sm font-medium">{module?.title ?? 'Moduł'}</span>
	</nav>
	<div class="min-h-0 flex-1 overflow-y-auto">
		{#if module}
			<ReactModuleHost {module} />
		{:else}
			<div class="p-6">
				<h1 class="text-xl font-semibold">Nie ma takiego modułu.</h1>
				<a href="/home" class="mt-3 inline-block text-sm underline">Wróć do pulpitu</a>
			</div>
		{/if}
	</div>
</div>
