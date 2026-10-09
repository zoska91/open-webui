# Oryginalny interfejs Open WebUI z Hermesem — różnice

Stan wdrożenia: 9 października 2026. Baza: Open WebUI 0.11.4, commit
8bd8b4fac5e059578ac0c74b3c18d11139f88b7d.

Przywrócone są oryginalne komponenty interfejsu: Sidebar, Chat, MessageInput,
Messages, Navbar, ChatControls, SettingsModal, wyszukiwanie, skróty, foldery,
notatki, kalendarz, kanały, workspace i panel administracyjny. Nie zastępuje ich
uproszczony panel Start/Czat. To nie oznacza, że każdy mechanizm AI Open WebUI
jest uruchomiony — poniżej znajduje się pełna lista ograniczeń naszego trybu.

## Wyłączone mechanizmy Open WebUI

1. **Jego własna ścieżka generowania odpowiedzi**: OpenAI/Anthropic compatible
   completions/responses/messages, Ollama, embeddings i middleware completions.
   Oryginalny komponent czatu korzysta z natywnego protokołu Hermesa.
2. **Wstrzykiwanie kontekstu do rozmowy**: system prompt, parametry generowania,
   ustawienia pamięci, folderowy/modelowy kontekst, filtry, identyfikatory
   narzędzi/skills i zmienne Open WebUI nie trafiają do Hermesa. Ustawienia można
   widzieć/zapisywać w interfejsie, ale nie konfigurują one jego agenta.
   Tekst wpisany lub świadomie wybrany jako szablon w edytorze jest wiadomością
   użytkownika; załączniki są przesyłane osobno do Hermesa.
3. **Functions / Pipes / Filters / Actions / plugin execution**: wyłączone
   ładowanie, instalowanie, uruchamianie i hooki przy wiadomościach/logowaniu.
   Katalog podstawowych metadanych pozostaje dostępny do odczytu.
4. **Narzędzia, skills, MCP/OpenAPI i terminale jako narzędzia Open WebUI**:
   ich wybór w OWUI nie uzbraja agenta i nie wykonuje operacji. Katalog skills
   może być organizowany jako dane UI. Narzędzia i integracje agenta obsługuje Hermes.
5. **RAG / Knowledge**: wyłączone indeksowanie, embedding, retrieval,
   reranking i automatyczne doklejanie dokumentów. Metadane istniejących
   kolekcji można odczytać; dodawanie/przetwarzanie ich treści jest zablokowane.
6. **Własna pamięć AI Open WebUI**: endpointy i opcja pamięci są wyłączone.
7. **Web search, code interpreter i generowanie obrazów Open WebUI**:
   ich osobne narzędzia i endpointy są wyłączone. Nie ogranicza to narzędzi
   dostępnych agentowi Hermes. Ręczne wykonywanie kodu przez użytkownika,
   formatowanie, kopiowanie i renderowanie odpowiedzi pozostają funkcjami UI.
8. **Dodatkowe zadania AI**: autouzupełnianie wpisywania, generowanie tytułów,
   tagów, kolejnych pytań, zapytań wyszukiwania, mixture-of-agents i podobne
   endpointy zadań Open WebUI są wyłączone. Tytuł z Hermesa może być pokazany
   bez dodatkowego wywołania modelu przez OWUI.
9. **Kompresja kontekstu Open WebUI**: wyłączona; OWUI nie streszcza rozmowy
   ani nie zmienia okna kontekstu Hermesa.
10. **Automatyzacje i scheduler AI Open WebUI**: nie uruchamiamy ich workerów
    ani endpointów wykonywania. Istniejące automatyzacje Hermesa pozostają jego.
11. **Event plugins i webhook dispatch Open WebUI**: publisher jest wyłączony,
    więc logowanie lub zapis rozmowy nie uruchomi dodatkowych skryptów.
12. **Osobne audio STT/TTS/voice Open WebUI**: endpointy audio są zablokowane.
    Przyciski zależne od tych usług nie są podłączone do usługi głosowej Hermesa.
13. **Połączenia z innymi modelami/dostawcami przez OWUI**: OpenAI/Ollama,
    direct connections, direct integrations, pipelines i ich konfiguracja
    runtime są wyłączone. Selektor udostępnia jedną bramę „Hermes”; model,
    dostawcę i jego parametry ustawia się w Hermesie.
14. **OAuth Open WebUI dla integracji**: jego ścieżki OAuth nie są dostępne
    w tym adapterze. Integracje agenta autoryzuje Hermes.

## Funkcje UI, które nie są jeszcze podłączone do natywnego protokołu

15. **Regeneracja i edycja wcześniejszego turnu**: adapter nie nadpisuje
    ani nie obcina historii Hermesa; próba ponownego wysłania wcześniejszego
    turnu kończy się wyraźnym komunikatem, bez wywołania modelu.
    Widok/edycja danych UI nie są zmianą natywnej pamięci agenta.
16. **Continue i regeneracja z dodatkową instrukcją**: te akcje nie są
    podłączone; adapter wyświetla komunikat zamiast tworzyć własny prompt.
17. **Fork / Clone rozmowy w OWUI**: zablokowane, dopóki nie mapujemy ich
    na prawdziwe rozgałęzienia Hermesa. Eksport/import danych UI pozostają.
18. **Porównywanie wielu modeli/kolumn**: wyłączone w wysyłaniu wiadomości;
    jeden czat jest jedną sesją Hermesa.
19. **Stare rozmowy OWUI bez przypisanej sesji Hermes**: nie odtwarzamy ich
    historii jako nowego promptu. Dalsza rozmowa wymaga otwarcia właściwego
    oryginału z listy Hermesa lub rozpoczęcia nowej sesji.

## Inne różnice względem standardowej instalacji

20. **Logowanie**: pominięte zgodnie z decyzją o prywatnej, jednoosobowej
    instalacji. Backend nadal ustanawia sesję aplikacji.
21. **Historia i wyszukiwanie**: do oryginalnego sidebaru kopiujemy metadane
    200 najnowszych sesji Hermesa. Ich pełna historia ładuje się po otwarciu
    rozmowy. Wyszukiwanie treści w OWUI obejmuje kopie zapisane w jego bazie;
    nie jest globalnym wyszukiwaniem całej bazy Hermesa.
22. **Załączniki**: pliki są przechowywane w OWUI bez jego ekstrakcji/RAG.
    Obrazy, PDF i inne pliki przekazuje się do natywnych metod Hermesa.
    Limit transportu wynosi 10 MiB na plik. Zewnętrzne URL oraz referencje
    typu knowledge/collection/folder/note/chat nie są pobierane automatycznie
    ani zamieniane przez OWUI w kontekst; należy dołączyć rzeczywisty plik.
    Edycja treści przechowywanego pliku przez endpoint wymagający reindeksacji
    jest wyłączona; pobieranie i usuwanie są dostępne.
23. **Dialogi Hermesa**: dodatkowy modal w oryginalnym czacie obsługuje
    clarify, approval, sudo i secret (oraz display.install.sudo). Odpowiedzi
    wysyła tylko po decyzji użytkownika. Pozostałe natywne typy żądań GUI
    nie są obsługiwane przez ten adapter.
24. **Dodatkowe trasy**: /hermes pozostaje widokiem diagnostycznym,
    /modules/<id> hostem React/TSX. /home przekierowuje do oryginalnego czatu /.
    Zniknął osobny uproszczony shell z wymuszonym ciemnym motywem. UI używa
    oryginalnych ustawień wyglądu i nawigacji.
25. **Role/permissions transportu**: natywne połączenie wymaga roli admin
    lub user, poprawnej sesji oraz tego samego Origin. API-key i JWT w query
    URL nie są akceptowane dla WebSocketu. Natywna brama przepuszcza metody
    rozmowy i dołączania plików oraz odpowiedzi na oczekujące pytania;
    administrację hostem, konfiguracją i pluginami Hermesa wykonuje jego UI.


26. **Szczegółowe zdarzenia i statystyki agenta**: adapter pokazuje tekst,
    reasoning i wyniki zakończonych narzędzi. Nie mapuje jeszcze wszystkich
    natywnych powiadomień, postępu narzędzi, usage/billing, artefaktów i reakcji
    Hermesa na odpowiednie elementy Open WebUI. Informacje te pozostają
    w jego własnym interfejsie; nie są zmieniane w agentowym runtime.
27. **Zmiany kopii rozmowy w OWUI**: zmiana nazwy, archiwizacja, usunięcie,
    edycja wiadomości, tagowanie, eksport/import i udostępnianie dotyczą
    danych aplikacji. Nie kasują ani nie zmieniają natywnej historii Hermesa.
    Usunięta kopia może zostać ponownie zaimportowana podczas synchronizacji.
    Synchronizacja dodaje brakujące rekordy; nie jest pełnym uzgadnianiem
    każdej późniejszej zmiany nazwy lub usunięcia w Hermesie.
28. **Czat tymczasowy OWUI**: pomija zapis kopii w jego bazie, ale nie
    ustanawia trybu incognito w Hermesie. Natywna sesja zachowuje jego
    zwykłe zasady zapisu historii. Przycisk nie gwarantuje braku zapisu
    rozmowy po stronie agenta.
29. **Ustawienia administracyjne AI**: oryginalny panel może zapisywać
    konfigurację aplikacji, lecz nie znosi granicy HERMES_ONLY. Włączenie
    opcji AI w bazie OWUI nie uruchomi jego generowania ani nie ustawi
    modelu, narzędzi lub promptu Hermesa.
    Wybrane zakładki ustawień AI odczytują zablokowane endpointy konfiguracji
    (np. audio/obrazy/RAG) i mogą zgłaszać niedostępność/błąd. Widok pozostaje
    oryginalny; konfigurację tych funkcji należy prowadzić w Hermesie.

## Dokładna granica API

Przepuszczamy CRUD UI/storage pod /api/v1/auths, users, chats, folders, notes,
calendars, channels, prompts, configs, groups, models, skills, evaluations,
scim, analytics, notifications i utils. Wyjątki:
- /api/v1/chats/<id>/compact, /fork, /clone są zablokowane.
- /api/v1/files jest dostępne jako surowy magazyn plików; końcówka
  /data/content/update jest zablokowana.
- tools/functions/knowledge/terminals: wyłącznie GET katalogu głównego,
  /list, /export, /base lub /id/<id>; pozostałe operacje są zablokowane.
- GET /api/config, /api/version, /api/version/updates, /api/changelog,
  /api/models oraz /api/models/base są dostępne.
- /api/hermes i /ws/socket.io są dostępne. WebSocket: tylko natywne
  /api/hermes/ws oraz oryginalne zdarzenia UI /ws/socket.io.
- Pozostałe /api, /openai, /ollama, /oauth i /ws są zablokowane odpowiedzią
  403 z kodem hermes_runtime_only. Trasy statyczne i nawigacja UI pozostają.

Oryginalne permissions i kontrole ról nadal obowiązują na przepuszczonych
trasach. Uprawnienie do API nie oznacza uruchomienia modelu.

Lista nadpisanych flag: enable_plugins, enable_direct_connections,
enable_direct_integrations, enable_automations, enable_context_compaction,
enable_tool_permissions, enable_web_search, enable_code_interpreter,
enable_image_generation, enable_autocomplete_generation, enable_memories,
enable_user_webhooks. Pozostałe flagi i konfiguracja są oryginalne, zależne od
wdrożenia — nie traktujemy funkcji niewłączonej w bazowej konfiguracji jako
dodatkowej blokady naszego adaptera.

Flagi wdrożenia ustawione na False: WEBUI_AUTH, ENABLE_LOGIN_FORM, ENABLE_SIGNUP,
ENABLE_OPENAI_API, ENABLE_OLLAMA_API, ENABLE_PLUGINS, ENABLE_TITLE_GENERATION,
ENABLE_TAGS_GENERATION, ENABLE_FOLLOW_UP_GENERATION, ENABLE_AUTOCOMPLETE_GENERATION,
ENABLE_SEARCH_QUERY_GENERATION i ENABLE_RETRIEVAL_QUERY_GENERATION.
ENABLE_PERSISTENT_CONFIG pozostaje True; HERMES_ONLY jest True.
