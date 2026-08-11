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

  // "Strongest qualifying signal per strategy" tiles shipped "overall rank
  // #undefined" for months: the card was built before render() assigned .rank.
  // The tiles must carry a real rank, and it must be the SAME rank the table's
  // Rank column shows for that arm - they are the same ordering or they are
  // lying. "-" is legitimate only for an arm the deduped ranking excludes.
  const rankTiles = await page.evaluate(() => {
    const strip = td => { const c = td.cloneNode(true);
      c.querySelectorAll('.small,button').forEach(n => n.remove());
      return c.textContent.trim(); };
    const rows = [...document.querySelectorAll('#signals-table tr')].map(r => {
      const c = [...r.querySelectorAll('td')];
      return c.length > 4 ? { sym: strip(c[0]), rank: strip(c[1]), strat: strip(c[4]) } : null;
    }).filter(Boolean);
    return [...document.querySelectorAll('.tile')]
      .filter(el => /overall rank/.test(el.textContent))
      .map(el => {
        const k = el.querySelector('.k').textContent.trim();
        const sym = el.querySelector('.v').textContent.trim();
        const strat = k.split(' - ')[0].trim();
        const shown = (k.match(/overall rank\s+(\S+)/) || [])[1] || '';
        const row = rows.find(r => r.sym === sym && r.strat === strat);
        return { k, sym, strat, shown, tableRank: row ? row.rank : null };
      });
  });
  t('signals: strongest-per-strategy tiles render at least one rank',
    rankTiles.length > 0);
  t('signals: no "overall rank #undefined" tile (shipped broken until 2026-08-10)',
    rankTiles.every(x => !/undefined|NaN|null/.test(x.k)));
  t('signals: every tile rank is a number or the unranked marker',
    rankTiles.every(x => /^#\d+$/.test(x.shown) || x.shown === '-'));
  t('signals: at least one tile matched to a table row (cross-check is live)',
    rankTiles.some(x => x.tableRank !== null));
  t('signals: tile rank agrees with the table Rank column',
    rankTiles.every(x => x.tableRank === null ||
      (x.shown === '#' + x.tableRank) ||
      (x.shown === '-' && (x.tableRank === '-' || x.tableRank === '·'))));

  // ZSCORE filter -> min auto-drops to 0, book z rows show their research stats
  await page.selectOption('#s-strat', 'ZSCORE');
  await page.waitForTimeout(300);
  const minVal = await page.evaluate(() => document.getElementById('s-minn').value);
  t('ZSCORE filter auto-min 0', minVal === '0');
  /* This was 'KNX z row present with research note' from 08-04 to 08-10. KNX was
     that day's #1 BOOKSIG z row (book #1 by rsi3, as_of 08-03) - not a generator
     row, so freshness has nothing to do with it. The z book re-ranks by rsi3 on
     every daily build, so the ticker simply rotated out (08-07: KMI/WDC/TRP;
     08-10: WPC/TRP/BRX/WSC) and the check went red on data movement, not on a
     regression - it pinned a rotating value instead of the behavior it was for.
     It was weak in a second way: the two substrings were tested independently
     against the whole table, so the note could have come from a different row
     than the ticker and the check would still have been green.
     Re-pinned to the behavior, per row, symbol-agnostic: the ZSCORE view renders
     book rows, and each one's note matches whether the audited z book (ZBOOK,
     BOOKS.zscore_000 per_name) actually covers that symbol - covered names show
     the research stats and the executable-estimate factor, uncovered names say
     they have no per-name record. Same rule as the gate count below: assert the
     shape, not today's tickers. */
  const zRows = await page.evaluate(() => {
    const f = (typeof ZFACTOR !== 'undefined') ? ZFACTOR : null;
    // No <thead> on this table - the header is a plain <tr> of <th>, so select
    // on the presence of a data cell rather than on tbody.
    return [...document.querySelectorAll('#signals-table tr')].filter(r => r.querySelector('td')).map(r => {
      const txt = r.textContent.replace(/\s+/g, ' ').trim();
      const sym = r.querySelector('td').textContent.trim();
      return { sym, txt,
               inBook: typeof ZBOOK !== 'undefined' && ZBOOK.has(sym),
               stats: txt.includes('research stats'),
               noRec: txt.includes('no per-name record'),
               factor: txt.includes('exec est x' + f) };
    });
  });
  t('ZSCORE view renders book z rows', zRows.length > 0);
  t('every z row states its research-record status',
    zRows.length > 0 && zRows.every(r => r.stats !== r.noRec));
  t('z rows the audited book covers carry research stats + exec estimate',
    zRows.length > 0 && zRows.every(r => r.inBook ? (r.stats && r.factor) : r.noRec));
  console.log('  z rows:', zRows.map(r => r.sym).join(', ') || 'none');
  console.log('  z row text sample:', (zRows[0] ? zRows[0].txt : '').slice(0, 220));

  // --- Today <-> Signals correspondence -------------------------------------
  // The two tabs derived their buy lists separately and disagreed completely:
  // Today read BOOKSIG (Gap Widen + Z-Score, refreshed nightly in the cloud)
  // while Signals showed SIGNALS (RSI2 + MFI, from the Mac generator), and the
  // default "min 30 trades" floor deleted every book row on top of that. The
  // owner saw zero overlap between "today's top three" and the Signals tab.
  // Earlier tests left the strategy filter on ZSCORE; these assertions are
  // about the DEFAULT view the owner actually lands on, so reset first.
  await page.selectOption('#s-strat', 'ALL');
  await page.evaluate(() => { document.getElementById('s-minn').value = '30'; });
  await page.evaluate(() => document.getElementById('s-apply').click());
  await page.waitForTimeout(300);
  const corr = await page.evaluate(() => {
    const act = (typeof TODAY_BUYS !== 'undefined' && TODAY_BUYS.act) || [];
    const html = document.getElementById('signals-table').innerHTML;
    const marked = [...document.querySelectorAll('#signals-table tr')]
      .filter(tr => /TODAY(&#039;|')S BUY/.test(tr.innerHTML)).length;
    return { n: act.length, marked,
      allPresent: act.every(b => html.includes(b.sym)) };
  });
  t('today: buy list is published for the Signals tab to read', corr.n >= 0);
  t('signals: every Today buy is present in the default view', corr.allPresent);
  t('signals: every Today buy is marked TODAY\'S BUY', corr.marked === corr.n);
  const cnt = await page.evaluate(() => document.getElementById('s-count').innerText);
  t('signals: count line reports the Today overlap',
    corr.n === 0 || /TODAY'S BUY row/.test(cnt));
  t('signals: book rows are exempt from the min-trades floor',
    /book rows? \(Gap Widen \/ Z-Score\) always shown/.test(cnt));
  // A row from a pipeline that did not refresh must not still claim to be NEW.
  const staleNew = await page.evaluate(() => {
    // Resolve the column by header, not by a hardcoded index - the row shape
    // has changed before and a silently-wrong index makes this assert nothing.
    const hdr = [...document.querySelectorAll('#signals-table th')]
      .map(h => h.getAttribute('data-k'));
    const iAsof = hdr.indexOf('as_of'), iNew = hdr.indexOf('new_today');
    if (iAsof < 0 || iNew < 0) return -1;
    const rows = [...document.querySelectorAll('#signals-table tr')].slice(1);
    const newest = rows.map(r => (r.querySelectorAll('td')[iAsof] || {}).innerText || '')
      .reduce((m, d) => d > m ? d : m, '');
    return rows.filter(r => {
      const asof = (r.querySelectorAll('td')[iAsof] || {}).innerText || '';
      const cell = (r.querySelectorAll('td')[iNew] || {}).innerHTML || '';
      return asof && asof < newest && /chip info">NEW</.test(cell);
    }).length;
  });
  t('signals: stale rows do not wear a NEW chip', staleNew === 0);
  t('signals: the stale-NEW check resolved its columns', staleNew >= 0);

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
  // Asserted BOTH ways on purpose. The original hard-coded "banner present",
  // which only held while the generator feed was stuck at 2026-07-31; once the
  // feed caught up the assertion failed on a page that was behaving correctly.
  // The real invariant is the banner appearing exactly when the dates diverge -
  // a banner on aligned dates would be just as wrong as none on mixed dates.
  const freshness = await page.evaluate(() => {
    const bs = (typeof BOOKSIG !== 'undefined' && BOOKSIG && BOOKSIG.as_of) || null;
    const sg = ((typeof SIGNALS !== 'undefined' && SIGNALS && SIGNALS.signals) || [])
      .reduce((m, x) => x.as_of && x.as_of > m ? x.as_of : m, '') || null;
    return { bs, sg, diverged: !!(bs && sg && bs !== sg) };
  });
  t('header: mixed-date banner iff BOOKSIG and SIGNALS diverge'
    + ` (booksig ${freshness.bs}, signals ${freshness.sg})`,
    freshness.diverged
      ? (hdr.includes('MIXED DATES') && hdr.includes('did NOT refresh in this build'))
      : !hdr.includes('MIXED DATES'));
  t('header: names the build source', /build .*github-actions|build .*\d{4}-\d{2}-\d{2}/.test(hdr));
  // HEALTH is stamped only by the cloud workflow; a Mac build refreshes the
  // blobs and pushes without touching it. The pipeline line must (a) show the
  // newest data bar, (b) carry the stamp-lag NOTE exactly when the data
  // postdates the stamp, and (c) never render earnings:0 as a bare number -
  // zero means Z-Score's pre-earnings exit ran with the gate open. Asserted
  // both ways, same rule as the mixed-date banner above.
  const hb = await page.evaluate(() => {
    const data = [(typeof TRACK !== 'undefined' && TRACK && TRACK.as_of) || '',
      (typeof BOOKSIG !== 'undefined' && BOOKSIG && BOOKSIG.as_of) || '',
      (typeof SHADOW !== 'undefined' && SHADOW && SHADOW.as_of) || '',
      (typeof SIGNALS !== 'undefined' && SIGNALS && SIGNALS.signals ?
        SIGNALS.signals.reduce((m, x) => (x.as_of || '') > m ? (x.as_of || '') : m, '') : '')]
      .filter(Boolean).reduce((m, d) => d > m ? d : m, '');
    return { data,
      stamp: ((typeof HEALTH !== 'undefined' && HEALTH && HEALTH.build) || '').slice(0, 10),
      earn: (typeof HEALTH !== 'undefined' && HEALTH) ? HEALTH.earnings : null };
  });
  // Scope these to the pipeline-OK line itself: "data through" is a substring
  // of the separate "Price data through" banner, so matching the joined header
  // would go green with the pipeline clause deleted (caught by mutation test).
  const pline = await page.evaluate(() =>
    [...document.querySelectorAll('header .sub')]
      .map(e => e.textContent).find(s => s.startsWith('pipeline OK')) || '');
  t('header: pipeline line present', pline.length > 0);
  t('header: pipeline line shows the newest data bar',
    !hb.data || pline.includes('data through ' + hb.data));
  t('header: stamp-lag NOTE iff data postdates the HEALTH stamp'
    + ` (data ${hb.data}, stamp ${hb.stamp})`,
    (hb.data && hb.stamp && hb.data > hb.stamp)
      ? pline.includes('data postdates this stamp')
      : !pline.includes('data postdates this stamp'));
  t('header: earnings 0 is labelled inert, never a bare count',
    hb.earn === 0 ? pline.includes('INERT in this build')
                  : !pline.includes('INERT in this build'));
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
