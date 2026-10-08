<script lang="ts">
	import ReactModuleHost from '$lib/components/modules/ReactModuleHost.svelte';
	import { getApplicationModule } from '$lib/modules/registry';

	const dashboard = getApplicationModule('dashboard');
</script>

{#if dashboard}
	<ReactModuleHost module={dashboard} />
{/if}
