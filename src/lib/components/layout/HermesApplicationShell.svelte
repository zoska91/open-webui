<script lang="ts">
	import { page } from '$app/stores';
	import { applicationModules } from '$lib/modules/registry';
	import { WEBUI_NAME } from '$lib/stores';

	$: navigation = [
		{ id: 'home', title: 'Start', path: '/home', icon: '⌂' },
		{ id: 'chat', title: 'Czat', path: '/hermes', icon: '◌' },
		...applicationModules.filter((module) => module.id !== 'dashboard')
	];
</script>

<div class="hermes-application-shell dark">
	<aside aria-label="Menu aplikacji">
		<a class="brand" href="/home">
			<img src="/static/favicon.png" alt="" width="28" height="28" />
			<span>{$WEBUI_NAME}<small>Hermes · Zofia</small></span>
		</a>
		<nav>
			{#each navigation as item (item.id)}
				<a
					href={item.path}
					class:active={$page.url.pathname === item.path || $page.url.pathname.startsWith(item.path + '/')}
					aria-current={$page.url.pathname === item.path ? 'page' : undefined}
				>
					<span aria-hidden="true" class="nav-icon">{item.icon}</span>{item.title}
				</a>
			{/each}
		</nav>
		<div class="sidebar-footer">Twoje aplikacje<small>Open WebUI · Hermes</small></div>
	</aside>
	<main id="main-content"><slot /></main>
</div>

<style>
	.hermes-application-shell { display: flex; width: 100%; height: 100dvh; overflow: hidden; background: #0d1117; color: #e7ecf3; }
	aside { display: flex; flex: 0 0 220px; flex-direction: column; border-right: 1px solid #232b36; padding: 24px 14px; background: #121821; }
	.brand { display: flex; gap: 12px; align-items: center; padding: 0 10px 30px; font-size: 15px; font-weight: 650; }
	.brand img { border-radius: 8px; }
	.brand small, .sidebar-footer small { display: block; margin-top: 4px; color: #8793a4; font-size: 11px; font-weight: 400; }
	nav { display: flex; flex-direction: column; gap: 6px; }
	nav a { display: flex; gap: 12px; align-items: center; min-height: 44px; padding: 10px 12px; border-radius: 9px; color: #aeb9c8; font-size: 14px; }
	nav a:hover { background: #1c2634; color: #fff; }
	nav a.active { background: #24354a; color: #eef5ff; }
	.nav-icon { width: 20px; text-align: center; font-size: 20px; }
	.sidebar-footer { margin-top: auto; padding: 18px 12px 0; color: #8793a4; font-size: 12px; }
	main { min-width: 0; flex: 1; height: 100%; overflow: auto; }
	@media (max-width: 767px) {
		.hermes-application-shell { flex-direction: column; }
		aside { flex: none; padding: 10px 12px; border-right: 0; border-bottom: 1px solid #232b36; }
		.brand { padding: 0 4px 8px; font-size: 13px; }
		.brand small { display: none; }
		.brand img { width: 22px; height: 22px; }
		nav { flex-direction: row; overflow-x: auto; }
		nav a { flex: none; min-height: 40px; padding: 7px 12px; }
		.sidebar-footer { display: none; }
		main { min-height: 0; }
	}
</style>
