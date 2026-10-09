import type { ModuleRuntimeContext } from './types';

interface RuntimeOptions {
	moduleId: string;
	userId: string;
	userName: string;
	navigate: ModuleRuntimeContext['navigate'];
}

/** Constructed after mount: storage and app authentication are browser-only. */
export const createModuleRuntime = ({
	moduleId,
	userId,
	userName,
	navigate
}: RuntimeOptions): ModuleRuntimeContext => {
	const preferencePrefix = `application-module:${userId}:${moduleId}:`;

	return {
		locale: 'pl-PL',
		timeZone: 'Europe/Warsaw',
		userName,
		navigate,
		async getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
			// Never forward the app's session token to an arbitrary origin.
			if (!path.startsWith('/api/') || path.includes('\\')) {
				throw new Error('Moduł może pobierać dane wyłącznie z API tej aplikacji.');
			}
			const token = localStorage.getItem('token');
			const response = await fetch(path, {
				method: 'GET',
				credentials: 'same-origin',
				headers: {
					Accept: 'application/json',
					...(token ? { Authorization: `Bearer ${token}` } : {})
				},
				signal
			});
			if (!response.ok) {
				throw new Error(`Nie udało się pobrać danych (${response.status}).`);
			}
			return (await response.json()) as T;
		},
		preferences: {
			get(key) {
				try {
					return localStorage.getItem(`${preferencePrefix}${key}`);
				} catch {
					return null;
				}
			},
			set(key, value) {
				try {
					localStorage.setItem(`${preferencePrefix}${key}`, value);
				} catch {
					// A blocked/full browser storage must not break the module.
				}
			}
		}
	};
};
