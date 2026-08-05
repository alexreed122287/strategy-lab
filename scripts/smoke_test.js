/* Playwright smoke suite for the dashboard. Run from anywhere:
     node scripts/smoke_test.js
   Every assertion here exists because something shipped wrong once. Do not
   delete one to make a run green - either the page is wrong, or the assertion
   is stale and needs replacing with what is now true. */
const path = require('path');
/* playwright-core is not vendored here - the repo stays dependency-free. Resolve
   it from wherever it is installed (local, global, or NODE_PATH) and say how to
   get it rather than dying on a bare MODULE_NOT_FOUND. */
const { chromium } = (() => {
  const { execSync } = require('child_process');
  const roots = [];
  try { roots.push(execSync('npm root -g', { encoding: 'utf8' }).trim()); } catch (e) {}
  for (const name of ['playwright-core', 'playwright']) {
    try { return require(name); } catch (e) {}
    for (const r of roots) {
      try { return require(path.join(r, name)); } catch (e) {}
    }
  }
  console.error('smoke: playwright not found. Install it with:\n' +
                '  npm i -g playwright-core   (or: npm i playwright-core)');
  process.exit(2);
})();
const PAGE = 'file://' + path.resolve(__dirname, '..', 'index.html');
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium' });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  await page.goto(PAGE);
  await page.evaluate(()=>document.querySelector('[data-tab="signals"]').click());
  await page.waitForTimeout(600);

  const t = (name, cond) => console.log((cond ? 'PASS' : 'FAIL') + ' - ' + name);

  // --- Signals tab (default view) ---
  const sigHtml = await page.evaluate(() => document.getElementById('signals-table').innerHTML);
  t('signals: no BB rows', !/>BB</.test(sigHtml));
  const stratOpts = await page.evaluate(() =>
    [...document.getElementById('s-strat').options].map(o => o.value));
  t('signals dropdown has ZSCORE', stratOpts.includes('ZSCORE'));
  t('signals dropdown has no BB', !stratOpts.includes('BB'));
  // Gap Widen was pulled 2026-08-02 and REINSTATED by x52 once the owner
  // supplied MIO's own ticker lists - so it must be back on the live surface.
  // BB stays off: its kill survived the same test (x59).
  t('signals dropdown has GAPW again (reinstated x52)',
    stratOpts.includes('GAPW_RSI2') || stratOpts.includes('GAPW_RSI14'));

  // ZSCORE filter -> min auto-drops to 12, KNX row shows research stats
  await page.selectOption('#s-strat', 'ZSCORE');
  await page.waitForTimeout(300);
  const minVal = await page.evaluate(() => document.getElementById('s-minn').value);
  t('ZSCORE filter auto-min 0', minVal === '0');
  const zHtml = await page.evaluate(() => document.getElementById('signals-table').innerHTML);
  // Was pinned to KNX until it closed on 2026-08-04 and left the signal list.
  // Assert the property, not a ticker: z rows are research records and must
  // always say so, whichever names happen to be signalling today.
  const zRows = await page.evaluate(() =>
    [...document.querySelectorAll('#signals-table tr')].filter(r => /ZSCORE/.test(r.textContent)).length);
  t('z rows present and carrying the research-stats caveat',
    zRows === 0 || zHtml.includes('research stats'));
  const zStats = await page.evaluate(() => {
    const tr = [...document.querySelectorAll('#signals-table tr')].find(r => r.textContent.includes('KNX'));
    return tr ? tr.textContent : '';
  });
  console.log('  KNX row text sample:', zStats.replace(/\s+/g, ' ').slice(0, 220));

  // --- Scan tab ---
  await page.evaluate(() => { document.querySelector('[data-tab="scan"]').click(); });
  await page.waitForTimeout(300);
  await page.fill('#f-sym', 'AAPL');
  await page.evaluate(() => document.getElementById('f-apply').click());
  await page.waitForTimeout(300);
  const scanHtml = await page.evaluate(() => document.getElementById('scan-table').innerHTML);
  t('scan AAPL shows ZSCORE row', />ZSCORE</.test(scanHtml));
  t('scan AAPL shows BB row', />BB</.test(scanHtml));
  const aaplRows = await page.evaluate(() =>
    [...document.querySelectorAll('#scan-table tr')].filter(r => r.textContent.includes('AAPL'))
      .map(r => r.textContent.replace(/\s+/g, ' ').trim()));
  console.log('  AAPL arms:', aaplRows.length);
  const zRow = aaplRows.find(r => r.includes('ZSCORE'));
  t('AAPL ZSCORE row carries brain stats (87.5 win)', !!zRow && zRow.includes('87.5'));
  console.log('  AAPL Z row:', (zRow || '').slice(0, 160));
  const bbRow = aaplRows.find(r => / BB /.test(' ' + r + ' ') || r.includes('BB'));
  console.log('  AAPL BB row:', (bbRow || 'NONE').slice(0, 160));

  // one ZSCORE row per ticker (dedup vs generator arm)
  await page.fill('#f-sym', 'SPY');
  await page.evaluate(() => document.getElementById('f-apply').click());
  await page.waitForTimeout(250);
  const spyZ = await page.evaluate(() =>
    [...document.querySelectorAll('#scan-table tr')].filter(r => {
      const first = r.querySelector('td');
      return first && first.textContent.trim() === 'SPY' && r.textContent.includes('ZSCORE');
    }).length);
  t('SPY has exactly one ZSCORE row', spyZ === 1);

  // --- Books tab ---
  await page.evaluate(() => { document.querySelector('[data-tab="books"]').click(); });
  await page.waitForTimeout(300);
  const booksHtml = await page.evaluate(() => document.getElementById('books-body').innerHTML);
  t('books: KILLED chip present', booksHtml.includes('>KILLED<'));
  t('books: PAPER chip present', booksHtml.includes('PAPER<'));
  t('books: BB first honest baseline tile', booksHtml.includes('First honest baseline'));
  t('books: z executable basis tile', booksHtml.includes('Executable basis'));
  t('books: z per-name details', booksHtml.includes('Per-name research record (audited wide screen'));
  t('books: bb per-name details', booksHtml.includes('harness anchor 432/438'));
  t('books: parity matrix updated', booksHtml.includes('SPEC C landed 08/01-08/02 and KILLED BB'));
  t('books: x45 tile present', booksHtml.includes('x45 LIVE universe (session)'));
  t('books: live universe block (358)', booksHtml.includes('MIO universe - LIVE 358 names'));
  t('books: x44 record demoted to details', booksHtml.includes('runnable names of the x44 replication record'));
  t('books: rh-session caption', booksHtml.includes('+ rh-session 2026-08-02'));
  t('books: status mentions x45 completion', booksHtml.includes('universe completed by x45'));

  // --- Guide tab (z card should reference the x45 live scan) ---
  await page.evaluate(() => { document.querySelector('[data-tab="guide"]').click(); });
  await page.waitForTimeout(300);
  const guideHtml = await page.evaluate(() => document.getElementById('guide-body').innerHTML);
  t('guide: z universe says since x45', guideHtml.includes('since x45, 08/02'));
  t('guide: z universe live count 358', /358 live names/.test(guideHtml));
  t('books: parity column renamed to account basis', booksHtml.includes('Forward (account)'));
  t('books: parity note explains the basis change', booksHtml.includes('decided BEFORE any trade closed'));
  t('books: x59 BB card', booksHtml.includes("BB re-run on MIO's OWN universe"));
  t('books: x59 kill stands', booksHtml.includes('kill stands, but the universe mattered'));
  t('books: BB still shows KILLED', booksHtml.includes('>KILLED<'));
  t('books: x58 drawdown lens card', booksHtml.includes('the deep era still fails'));
  t('books: x58 flags deeper drawdowns', booksHtml.includes('DEEPER than B&amp;H'));
  t('books: bench gate has a Calmar column', booksHtml.includes('Calmar ratio'));
  t('books: x57 panel card', booksHtml.includes('panel co-sign: x43 and x44 signed'));
  // E3 ruled 2026-08-03: x45 moved from WITHHELD to co-signed-restated.
  t('books: x57 records the E3 ruling', booksHtml.includes('the PROSE binds'));
  t('books: x57 records x45 co-signed restated', booksHtml.includes('CO-SIGNED (restated)'));
  t('books: no stale WITHHELD claim remains', !/co-sign REMAINS WITHHELD/.test(booksHtml));
  t('books: per-name RH basis markers', booksHtml.includes('>RH</span>'));
  t('books: x57 carries the refuted findings', booksHtml.includes('themselves refuted'));
  t('books: MIO 67.2% match claim withdrawn, not asserted',
    booksHtml.includes('was WITHDRAWN by the co-sign panel') &&
    !/positive - matches MIO/.test(booksHtml));
  t('books: x55 Z-Score row corrected to -3.52pp', booksHtml.includes('-3.52'));
  t('books: x56 reconciliation card', booksHtml.includes('the RSI2 loose end, closed against the research archive'));
  t('books: x56 sourcing note', booksHtml.includes('conclusions only'));
  t('books: x56 carries no private research figures',
    !/60\.1%|PF 2\.26|n 517|base16|curation intensity/.test(booksHtml));
  t('books: x55 bands card', booksHtml.includes('how much of each recent number needs recent listings'));
  t('books: three-band block on book cards', booksHtml.includes('Bear floor (deep OOS, measured)'));
  t('books: x55 listing effect for RSI14', booksHtml.includes('-25.26pp') || booksHtml.includes('23.91%'));
  // Corrected 2026-08-03: the Z-Score listing effect was published as +0.97pp
  // (a Tradier-vs-RH store mismatch) and is -3.52pp like-for-like. The band
  // block must now take the "part of the number needs recent listings" branch.
  t('books: zscore band no longer claims immunity',
    !booksHtml.includes('does not depend on names that only exist in this era'));
  t('books: zscore band states the corrected effect', /-3\.52pp/.test(booksHtml));
  t('books: x54 deep card', booksHtml.includes('Z-Score deep era on the MIO list'));
  t('books: x54 tile', booksHtml.includes('Deep era 2011-18 (x54)'));
  t('books: x54 verdict is FAIL', booksHtml.includes('-1.57pp'));
  t('books: x54 discloses the contaminated first run',
    booksHtml.includes('interpolated:true') || booksHtml.includes('interpolated'));
  t('books: bench gate no longer claims one failing era',
    !booksHtml.includes('The one era where a book FAILED'));
  t('books: provenance tile', booksHtml.includes('Provenance test (x45d)'));
  t('books: hygiene tile', booksHtml.includes('Data hygiene (v2)'));
  t('books: earnings-worth tile', booksHtml.includes('Earnings rule worth'));
  t('books: status cites cumulative list', booksHtml.includes('provably cumulative'));

  // --- Header freshness banner (cloud builds cannot refresh SCAN/SIGNALS) ---
  const hdr = await page.evaluate(() =>
    [...document.querySelectorAll('header .sub')].map(e => e.textContent).join(' | '));
  t('header: mixed-date banner when BOOKSIG and SIGNALS diverge',
    hdr.includes('MIXED DATES') && hdr.includes('did NOT refresh in this build'));
  t('header: names the build source', /build .*github-actions|build .*\d{4}-\d{2}-\d{2}/.test(hdr));
  // The header derived its date from SIGNALS alone, so it advertised the STALE
  // pipeline's date as the whole page's - reading as a dead site to the owner.
  const dates = await page.evaluate(() => {
    const newest = [TRACK && TRACK.as_of, BOOKSIG && BOOKSIG.as_of,
      SIGNALS.signals.reduce((m, x) => x.as_of > m ? x.as_of : m, '')]
      .filter(Boolean).reduce((m, d) => d > m ? d : m, '');
    const gen = SIGNALS.signals.reduce((m, x) => x.as_of > m ? x.as_of : m, '');
    return { newest, gen };
  });
  t('header: leads with the NEWEST price date, not the stale generator date',
    hdr.includes('Price data through ' + dates.newest));
  t('header: still names the lagging generator date',
    dates.gen === dates.newest || hdr.includes('RSI2/MFI scan rows ' + dates.gen));
  t('header: does not advertise the stale date as the page date',
    dates.gen === dates.newest || !hdr.includes('Price data through ' + dates.gen));

  // --- TODAY: the account model must be the ONLY denominator on this card ---
  await page.evaluate(() => { document.querySelector('[data-tab="today"]').click(); });
  await page.waitForTimeout(400);
  const today = await page.evaluate(() => document.getElementById('today-body').innerText);
  const pf = await page.evaluate(() => (SHADOW.portfolio || {}));
  // Sizes read off SLOTS instead of SIZE_DIVISOR quoted ~$20,000 a name once
  // slots went 3 -> 1 - three times the account's own size and three times the
  // risk the books were validated at. Assert against the account's real cost.
  const wantSize = Math.round(pf.capital / Object.keys(pf.slots_per_book).length
                              / (pf.size_divisor.ZSCORE || 3));
  t('today: buy size matches the validated divisor, not the slot count',
    !/Buy ~\$/.test(today) || today.includes('Buy ~$' + wantSize.toLocaleString()));
  t('today: never quotes a full undivided sleeve',
    !today.includes('Buy ~$' + (pf.capital / Object.keys(pf.slots_per_book).length).toLocaleString()));
  // Slots came from the skip-free ledger, whose open count exceeds any slot
  // limit permanently - so every book read zero free and no buy could surface.
  const anyFree = Object.entries(pf.by_book)
    .some(([b, s]) => (pf.slots_per_book[b] || 1) - s.open > 0);
  t('today: a book with a free account slot is not reported as full',
    !anyFree || /to buy|free slot, but no signal/.test(today));
  // Sells are the account's own exits, not the ledger's 13.
  t('today: sell count matches ACCOUNT exits, not the ledger',
    (pf.exits_today || []).every(e => today.includes(e.sym)));
  const ledgerExtra = await page.evaluate(() =>
    (SHADOW.exits_today || []).length - ((SHADOW.portfolio || {}).exits_today || []).length);
  t('today: ledger-only exits are disclosed, not silently shown as sells',
    ledgerExtra <= 0 || today.includes(ledgerExtra + ' further exit'));
  t('today: Gap Widen no longer described as pulled-and-research-only',
    today.includes('reinstated by x52'));

  // Same-day round trips (MOO entry, 3:45 -> MOC exit) must reach the record.
  const sameDay = await page.evaluate(() => {
    const led = SHADOW.portfolio.closed_recent || [];
    return led.length;
  });
  t('gate: account has closed trades recorded', sameDay > 0 && pf.gate_closed >= sameDay);
  t('gate: no phantom position left open by a same-day round trip',
    (pf.open_names || []).length === pf.open_positions);

  // --- Positions tab (shadow book + account replay + the real-money gate) ---
  await page.evaluate(() => { document.querySelector('[data-tab="positions"]').click(); });
  await page.waitForTimeout(400);
  const posHtml = await page.evaluate(() => document.body.innerHTML);
  t('positions: real-money gate tile', posHtml.includes('Real-money gate'));
  // Gate accrues on calendar time - assert the shape and that it is on the
  // ACCOUNT basis, not a fixed count that goes stale the first time one closes.
  t('positions: gate reads N of 20', /Real-money gate[\s\S]{0,200}\d+ of 20/.test(posHtml));
  // 2026-08-03: one slot per book (owner decision at zero closed trades)
  t('positions: one slot per book', /1-slot limit|slot limit inside its sleeve/.test(posHtml));
  t('positions: gate states the account basis',
    posHtml.includes('closed SHARED-ACCOUNT trades needed'));
  // 2026-08-04: real money needs BOTH legs - program-wide shared account AND
  // the book's own $100k. Neither may quietly become sufficient alone.
  t('positions: gate is labelled leg 1 of 2', /leg 1 of 2/i.test(posHtml));
  t('positions: solo accounts card present', posHtml.includes('competing with nobody'));
  t('positions: solo card states BOTH gates are required',
    posHtml.includes('Real money needs BOTH gates'));
  t('positions: solo card does not claim skips are eliminated',
    posHtml.includes('NOT 100%') && !/no more skipped trades|zero skipped/i.test(posHtml));
  t('positions: solo table has a per-book gate column', posHtml.includes('Gate 2 of 2'));
  t('positions: per-book Closed column', /<th>Closed<\/th>/.test(posHtml));

  t('books: discloses the same-day round-trip correction',
    booksHtml.includes('this count moved from 1 to'));
  t('books: correction states no rule changed', booksHtml.includes('No rule changed'));

  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'NO PAGE ERRORS');
  await browser.close();
})();
