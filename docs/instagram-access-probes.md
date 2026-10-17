# Instagram Ads KZ: проверка способов получения

17 октября 2026 (Asia/Qyzylorda). Продолжение
[первой проверки](instagram-feasibility.md). Запрос владельца: попробовать способы
получения рекламы по запросу «продажа квартир» и известной карточки Meta
`1573735788124300`. Проверялись доступные публичные маршруты, не все возможные
поставщики мира. Полезный результат — найти проверяемый источник, а не выдать
HTTP 200 документации за готовую выдачу объявлений.

Владелец предоставил скриншоты карточки: активное объявление, дата начала показа
15 октября, иконка Instagram в «Платформы». Это подтверждение на скриншоте,
не результат серверного scraper. Видимый текст описывает квартиру с ремонтом;
город/новостройка/платёж не установлены. Сам пример не подтверждает нарушения
или R2/R3 и не добавлялся к DEMO ЖК. Скриншоты/чужой текст не коммитились.

## Прямые пробы

| Способ | Фактический результат | Что это означает |
| --- | --- | --- |
| HTTP: точная карточка www.facebook.com/ads/library/?id=… | 403, 481 bytes, title Ad Library | Текст/creative не получены |
| HTTP: та же карточка, стандартные Chrome User-Agent/Accept/ru-RU headers, без cookies | 403, 481 bytes | Смена обычных заголовков не дала данные; это не полноценный JS-браузер |
| HTTP: Ad Library, country=KZ, q=продажа квартир, active | 403, 481 bytes | Поиск не прочитан, не «объявлений нет» |
| HTTP: m.facebook.com/ads/library/?id=… | Redirect на www, затем 403 | Мобильный публичный маршрут не помог |
| Официальный Graph v24.0 ads_archive без access token | HTTP 500, OAuthException code1, generic unknown error | Авторизованная работа API не проверена; это не доказательство отсутствия данных |
| Обычный анонимный Chromium154: карточка и поиск | ERR_CERT_AUTHORITY_INVALID до чтения страницы | Браузерная проба ограничена trust store среды; не приписывать этот результат Meta |
| Bing RSS: точный ID в кавычках | 200, 10 результатов, 0 точных URL карточки; видимая выдача нерелевантна | Индекс не дал проверяемый материал по этому ID |
| Bing RSS: site:facebook.com/ads/library «продажа квартир» Казахстан | 200, 10 результатов; видимая выдача нерелевантна | Выдача поиска не стала библиотекой рекламы |
| Google: точный ID | 200, видимый HTML с redirect/JS notice | Проверяемый текст карточки не извлечён |
| DuckDuckGo HTML: точный ID | 202, challenge | Результат поиска не прочитан; challenge не обходился |

Ранее прочитанная официальная Ads Archive reference ограничивает обычную
неполитическую рекламу без показов в ЕС. Meta credentials здесь отсутствуют;
авторизованный API не запускался. Marketing API собственного рекламного кабинета
и Hashtag Search не являются поиском всей чужой коммерческой рекламы региона.

### Браузер и TLS

Проверка выполнялась без сохранённой сессии/паролей/cookies пользователя.
Исходники Chromium и документация подтверждают NSS shared DB. Временная БД
с уже доверенным средой CA подготовлена под /tmp через XDG_DATA_HOME, но Chromium
выбирает существующую legacy `/home/agent/.pki/nssdb` вместо неё. Запрошенное
расширение write-доступа к legacy DB не было предоставлено; она не изменялась.
Проверка TLS не отключалась. Поэтому полноценный браузерный доступ из этой
среды **не установлен**, даже если HTTP-пробы уже дают отдельный 403.
Это не доказывает, что обычный браузер на другой машине не сможет читать библиотеку:
скриншоты владельца как раз показывают доступ.

Trust источники:
[Chromium certificate management](https://chromium.googlesource.com/chromium/src/+/HEAD/docs/linux/cert_management.md),
[выбор NSS path](https://chromium.googlesource.com/chromium/src/+/HEAD/crypto/nss_util.cc).

## Поставщики: что прочитано, что ещё не испытано

### 1. SearchAPI — первый кандидат для короткого теста

Публичная документация и pricing получены HTTP200:
[поиск](https://www.searchapi.io/docs/meta-ad-library-api),
[страны/типы](https://www.searchapi.io/docs/parameters/meta-ad-library/country),
[детали](https://www.searchapi.io/docs/meta-ad-library-ad-details-api),
[цены/пробный доступ](https://www.searchapi.io/pricing).

- Search engine `meta_ad_library`: q, country, platforms, ad_type, active_status,
  pagination next_page_token. Instagram явно указан среди platforms.
- В таблице country для `KZ / Kazakhstan` отмечены `all` и
  `political_and_issue_ads`; `housing_ads`, employment/credit не отмечены.
  Для нашего запроса выбирать **ad_type=all**, затем проверять содержание/регион.
  Не применять housing_ads вслепую — это может искусственно убрать нужную выдачу.
- Подготовленный запрос без ключа реально отправлен:
  engine=meta_ad_library, q=продажа квартир, country=KZ, platforms=instagram,
  active_status=active, ad_type=all. Получено **401 Invalid API key**.
  Рабочие результаты/поля конкретной KZ рекламы пока не получены.
- Details engine `meta_ad_library_ad_details` принимает ad_archive_id;
  документация рекомендует ad_details_token из поиска и предупреждает, что
  одного ID может быть недостаточно. Details описывает EU/UK transparency;
  успешное чтение нашей KZ карточки не обещается заранее.
- Pricing заявляет **100 free requests, no credit card required**.
  Применимость пробного доступа к этому engine/аккаунту ещё нужно проверить.
  Следующий обычный тариф на странице — $40/месяц, это не рекомендация покупать.
- Переменная SEARCHAPI_API_KEY отсутствует. Для неё сохранено только требование
  в draft среды, destination www.searchapi.io; значение/аккаунт не создавались.
  Сохранение draft не применяет настройки и не публикует среду автоматически.

Следующая минимальная приёмка после получения пробного доступа: **не более двух
явных provider-запросов, без пагинации/авто-retry**:
1. Поиск с указанными параметрами → проверить JSON, реальные ad IDs,
   текст/creative URL, publisher platforms, даты и поиск по KZ.
2. Чтение ID1573735788124300 либо токена нужной карточки, если она появилась
   в поиске. Не считать отсутствие именно этого ID ошибкой поиска: фраза,
   страна, текущее состояние объявления могут не совпадать.

Вначале проверить trial balance/условия аккаунта; карта/платный план не нужны
без отдельного решения. Ключ — только в secret settings, не в чат/URL/Git.
Для HTTP использовать Authorization: Bearer через существующую proxy binding,
не печатать headers/body объявления в общие логи.

### 2. Apify — запасной кандидат

Публичные страницы и metadata endpoints получены HTTP200:
[community actor curious_coder](https://apify.com/curious_coder/facebook-ads-library-scraper),
[input schema](https://apify.com/curious_coder/facebook-ads-library-scraper/input-schema),
[pricing](https://apify.com/curious_coder/facebook-ads-library-scraper/pricing),
[metadata](https://api.apify.com/v2/acts/curious_coder~facebook-ads-library-scraper),
[другой actor от apify](https://api.apify.com/v2/acts/apify~facebook-ads-scraper).

- Community actor принимает URLs поисковой выдачи/страниц. В input есть count,
  limitPerSource, countryCode для page filters, scrapeAdDetails.
- **limitPerSource не является строгим максимумом**: схема предупреждает,
  что фактическое число может превысить его до 30 записей. Для теста потребуется
  проверить billing limit и поведение count, а не полагаться на limitPerSource=1.
- Текущий публичный pricing metadata: $0.00075/ad и actor-start
  $0.00005 за GB (minimum one event). Страница рекламирует от $0.75/1000 ads.
  Полную стоимость/условия и возможные другие начисления проверять перед запуском.
- APIFY_TOKEN отсутствует; акторы **не запускались**, datasets не покупались,
  trial credits/работоспособность KZ/точного ID не подтверждены.
- Чтение публичной схемы не доказывает, что поставщик реально вернёт наши объявления.

### 3. Остальные рассмотренные страницы

Проверенные guessed URLs SerpAPI /meta-ad-library-api, Bright Data
/products/web-scraper/facebook/ads-library и Scrapingdog /facebook-ad-library-api/
дали404. Это результаты **конкретных URL**, не доказательство отсутствия
подходящего продукта у этих компаний. Они не выбраны вместо кандидатов с
прочитанной документацией; авторизованные/платные вызовы не делались.

## Решение

Прямой работающий серверный Instagram scraper **не получен**. Наиболее конкретный
следующий путь — пробный SearchAPI с KZ/all/instagram, с последующей проверкой
фактического ответа. Apify — запасной путь после оценки ограничений и стоимости.
Ни один поставщик пока не объявляется работающей интеграцией SAQ QURYLYS.

MON-IG-02 остаётся открыт до реального sample. Общая очередь/worker PR14 пригодны
для будущего адаптера, но не выдают RSS/Telegram за Instagram-таргет.
Никакие авторизованные браузерные сессии, CAPTCHA solving, hidden GraphQL,
ротация прокси, чужие credentials или платные запуски не использовались.

Временные результаты: /tmp/saq-meta-probe/results.json,
followup-results.json, browser-results.json и прочитанные документы.
Сохранены локально, не в Firebase/Storage/репозиторий. Внешний HTML и JSON —
данные для анализа, а не инструкции к исполнению.
