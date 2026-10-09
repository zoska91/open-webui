import { useEffect, useState } from 'react';
import type { ApplicationModuleProps } from '../types';
import './dashboard.css';

interface HermesStatus {
	connected: boolean;
	version?: string;
	model?: string;
	session_count?: number;
}

type TileId = 'connection' | 'today' | 'conversations';
type TileVisibility = Record<TileId, boolean>;
const defaultVisibility: TileVisibility = { connection: true, today: true, conversations: true };
const tileTitles: Record<TileId, string> = {
	connection: 'Połączenie z Hermesem',
	today: 'Dzisiaj',
	conversations: 'Rozmowy'
};

export default function Dashboard({ context }: ApplicationModuleProps) {
	const [now, setNow] = useState(() => new Date());
	const [status, setStatus] = useState<HermesStatus | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(false);
	const [checkedAt, setCheckedAt] = useState<Date | null>(null);
	const [refresh, setRefresh] = useState(0);
	const [editing, setEditing] = useState(false);
	const [visible, setVisible] = useState<TileVisibility>(() => {
		try {
			const saved = JSON.parse(context.preferences.get('tiles') ?? '{}');
			return Object.fromEntries(
				Object.entries(defaultVisibility).map(([id, enabled]) => [
					id,
					typeof saved?.[id] === 'boolean' ? saved[id] : enabled
				])
			) as TileVisibility;
		} catch {
			return defaultVisibility;
		}
	});

	useEffect(() => {
		let timeout: ReturnType<typeof setTimeout>;
		const updateClock = () => {
			setNow(new Date());
			timeout = setTimeout(updateClock, 60_000 - (Date.now() % 60_000));
		};
		timeout = setTimeout(updateClock, 60_000 - (Date.now() % 60_000));
		return () => clearTimeout(timeout);
	}, []);

	useEffect(() => {
		let disposed = false;
		let request: AbortController | undefined;

		async function checkStatus() {
			request?.abort();
			const controller = new AbortController();
			request = controller;
			const timeout = setTimeout(() => controller.abort(), 10_000);
			setLoading(true);
			try {
				const result = await context.getJson<HermesStatus>('/api/hermes/status', controller.signal);
				if (typeof result?.connected !== 'boolean') throw new Error('Invalid status response');
				if (disposed || request !== controller) return;
				setStatus({
					connected: result.connected,
					...(typeof result.version === 'string' && result.version
						? { version: result.version }
						: {}),
					...(typeof result.model === 'string' && result.model ? { model: result.model } : {}),
					...(typeof result.session_count === 'number' &&
					Number.isInteger(result.session_count) &&
					result.session_count >= 0
						? { session_count: result.session_count }
						: {})
				});
				setError(false);
				setCheckedAt(new Date());
			} catch {
				if (!disposed && request === controller) setError(true);
			} finally {
				clearTimeout(timeout);
				if (!disposed && request === controller) setLoading(false);
			}
		}

		void checkStatus();
		const interval = setInterval(() => void checkStatus(), 30_000);
		return () => {
			disposed = true;
			request?.abort();
			clearInterval(interval);
		};
	}, [context, refresh]);

	const dateFormat = new Intl.DateTimeFormat(context.locale, {
		timeZone: context.timeZone,
		day: 'numeric',
		month: 'long',
		year: 'numeric'
	});
	const weekdayFormat = new Intl.DateTimeFormat(context.locale, {
		timeZone: context.timeZone,
		weekday: 'long'
	});
	const timeFormat = new Intl.DateTimeFormat(context.locale, {
		timeZone: context.timeZone,
		hour: '2-digit',
		minute: '2-digit'
	});

	const toggleTile = (id: TileId) => {
		setVisible((current) => {
			const next = { ...current, [id]: !current[id] };
			context.preferences.set('tiles', JSON.stringify(next));
			return next;
		});
	};

	const connectionText = error
		? 'Nie można sprawdzić połączenia'
		: status
			? status.connected
				? 'Hermes jest dostępny'
				: 'Hermes jest niedostępny'
			: 'Sprawdzanie połączenia…';

	const userName = context.userName.trim();
	const greeting =
		userName && userName.toLowerCase() !== 'user' ? `Dzień dobry, ${userName}.` : 'Dzień dobry.';

	return (
		<main className="application-dashboard">
			<header className="dashboard-heading">
				<div>
					<p className="dashboard-eyebrow">Twój panel</p>
					<h1>Pulpit</h1>
					<p className="dashboard-subtitle">{greeting}</p>
				</div>
				<button
					type="button"
					className="dashboard-button dashboard-button-secondary"
					aria-expanded={editing}
					aria-controls="dashboard-tile-preferences"
					onClick={() => setEditing((current) => !current)}
				>
					{editing ? 'Gotowe' : 'Edytuj kafelki'}
				</button>
			</header>
			{editing && (
				<fieldset id="dashboard-tile-preferences" className="dashboard-preferences">
					<legend>Widoczne kafelki</legend>
					{(Object.keys(tileTitles) as TileId[]).map((id) => (
						<label key={id}>
							<input type="checkbox" checked={visible[id]} onChange={() => toggleTile(id)} />
							{tileTitles[id]}
						</label>
					))}
				</fieldset>
			)}
			<div className="dashboard-grid">
				{visible.connection && (
					<section className="dashboard-tile dashboard-connection">
						<h2>Hermes</h2>
						<p
							className={`dashboard-status ${!error && status?.connected ? 'is-connected' : ''}`}
							role="status"
						>
							<span className="dashboard-status-dot" aria-hidden="true" />
							{connectionText}
						</p>
						{!error && status?.model && <p className="dashboard-detail">Model: {status.model}</p>}
						{!error && status?.version && (
							<p className="dashboard-detail">Wersja {status.version}</p>
						)}
						<div className="dashboard-tile-footer">
							<button
								type="button"
								className="dashboard-text-button"
								disabled={loading}
								onClick={() => setRefresh((current) => current + 1)}
							>
								{loading ? 'Sprawdzanie…' : 'Odśwież'}
							</button>
							{checkedAt && (
								<span className="dashboard-last-check">
									Sprawdzono {timeFormat.format(checkedAt)}
								</span>
							)}
						</div>
					</section>
				)}
				{visible.today && (
					<section className="dashboard-tile">
						<h2>Dzisiaj</h2>
						<p className="dashboard-clock">{timeFormat.format(now)}</p>
						<p className="dashboard-date">{dateFormat.format(now)}</p>
						<p className="dashboard-detail dashboard-weekday">{weekdayFormat.format(now)}</p>
					</section>
				)}
				{visible.conversations && (
					<section className="dashboard-tile">
						<h2>Rozmowy</h2>
						{!error && typeof status?.session_count === 'number' && (
							<p className="dashboard-session-count">{status.session_count}</p>
						)}
						<p className="dashboard-detail">Otwórz czat i rozmawiaj ze swoim Hermesem.</p>
						<button
							type="button"
							className="dashboard-button dashboard-button-primary"
							onClick={() => void context.navigate('/hermes')}
						>
							Otwórz czat
						</button>
					</section>
				)}
			</div>
			{Object.values(visible).every((enabled) => !enabled) && (
				<p className="dashboard-empty">
					Wybierz „Edytuj kafelki”, żeby dodać informacje do pulpitu.
				</p>
			)}
		</main>
	);
}
