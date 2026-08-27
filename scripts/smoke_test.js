/* Playwright smoke suite for the dashboard. Run from anywhere:
     node scripts/smoke_test.js
   Every assertion here exists because something shipped wrong once. Do not
   delete one to make a run green - either the page is wrong, or the assertion
   is stale and needs replacing with what is now true. */
const path = require('path');
const fs = require('fs');
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
  /* Resolve a browser instead of hardcoding one path. '/opt/pw-browsers/chromium'
     does not exist on this Mac, so from 2026-08-19 every local build died here
     with "executable doesn't exist" - the render gate refuses to publish
     unverified, so the Mac stopped publishing entirely and index.html's
     SCAN/SIGNALS blobs (which only the Mac can generate) froze for a week
     while the cloud backstop kept refreshing everything else. Probe, and say
     what was tried when nothing is found. */
  const CANDIDATES = [
    process.env.CHROMIUM_PATH,
    '/opt/pw-browsers/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ].filter(Boolean);
  const exe = CANDIDATES.find(c => { try { return fs.existsSync(c); } catch (e) { return false; } });
  if (!exe) {
    console.error('smoke: no chromium binary found. Tried:\n  ' + CANDIDATES.join('\n  ') +
                  '\nSet CHROMIUM_PATH, or install Chrome.');
    process.exit(2);
  }
  const browser = await chromium.launch({ executablePath: exe });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('CONSOLE: ' + m.text()); });
  await page.goto(PAGE);
  await page.evaluate(()=>document.querySelector('[data-tab="signals"]').click());
  await page.waitForTimeout(600);

  // A FAIL must be machine-visible, not just a line a human has to read: the
  // suite used to exit 0 regardless, so nothing wired to it could ever block.
  const t = (name, cond) => {
    if (!cond) process.exitCode = 1;
    console.log((cond ? 'PASS' : 'FAIL') + ' - ' + name);
  };

  // --- Signals tab (default view) ---
  const sigHtml = await page.evaluate(() => document.getElementById('signals-table').innerHTML);
  t('signals: no BB rows', !/>BB</.test(sigHtml));
  const stratOpts = await page.evaluate(() =>
    [...document.getElementById('s-strat').options].map(o => o.value));
  /* The strategy dropdown is data-driven: it lists exactly the strats present
     in the view's row set (fresh vetted generator rows + today's book rows).
     'dropdown has ZSCORE' as an absolute went red on 08-14 when the z book
     produced its first zero-candidate day (z50 <= -1.5 is rare in a strong
     tape) while the freshness gate was already suppressing the stale
     generator rows - data movement, not a regression. Same defect class as
     the 08-13 tile checks: pin the iff, not today's data. ZSCORE and the
     GAPW pair are book-fed (ZSCORE generator rows are never vetted, GAPW is
     book-only), so the expectation mirrors the page's own sources. */
  const dropExpect = await page.evaluate(() => {
    const live = (typeof TRACK !== 'undefined' && TRACK && TRACK.as_of) ||
                 (typeof BOOKSIG !== 'undefined' && BOOKSIG && BOOKSIG.as_of) || '';
    const genVetted = st => ((typeof SIGNALS !== 'undefined' && SIGNALS.signals) || [])
      .some(x => x.strat === st && x.state !== 'WATCH' && (!live || x.as_of === live) &&
        !!(SCAN.tickers[x.sym] && SCAN.tickers[x.sym].strats[st] &&
           SCAN.tickers[x.sym].strats[st].vetted));
    const book = st => ((typeof BOOKSIG !== 'undefined' && BOOKSIG && BOOKSIG.rows) || [])
      .some(r => r.strat === st);
    return { z: genVetted('ZSCORE') || book('ZSCORE'),
             gapw: book('GAPW_RSI2') || book('GAPW_RSI14') };
  });
  t(`signals dropdown has ZSCORE iff z rows exist today (expected=${dropExpect.z})`,
    stratOpts.includes('ZSCORE') === dropExpect.z);
  t('signals dropdown has no BB', !stratOpts.includes('BB'));
  // Gap Widen was pulled 2026-08-02 and REINSTATED by x52 once the owner
  // supplied MIO's own ticker lists - so when its book has rows they must be
  // on the live surface. BB stays off: its kill survived the same test (x59).
  t(`signals dropdown has GAPW iff its book has rows (expected=${dropExpect.gapw})`,
    (stratOpts.includes('GAPW_RSI2') || stratOpts.includes('GAPW_RSI14')) === dropExpect.gapw);

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
  /* These tiles are built from the GENERATOR pool (RSI2/MFI), so they exist
     only when that feed is on the live bar. The freshness gate added 08-10
     drops every stale generator row from the ranking - the correct behavior
     for a cloud-only build, and the normal state between Mac generator runs.
     Asserting "at least one tile" unconditionally therefore went red on a
     page behaving perfectly: on the 08-13 build, SIGNALS sat at 08-11, 106
     rows were suppressed, and 0 tiles rendered. Same defect class the KNX
     check had - it pinned a transient data condition, not a behavior.
     Pinned both ways instead: tiles present iff the generator feed is live,
     absent iff it is stale. The absent case now PROVES the gate fired. */
  const genLive = await page.evaluate(() => {
    const live = (typeof TRACK !== 'undefined' && TRACK && TRACK.as_of) || '';
    const rows = (typeof SIGNALS !== 'undefined' && SIGNALS && SIGNALS.signals) || [];
    return !!live && rows.some(x => x.state !== 'WATCH' && x.as_of === live);
  });
  t(`signals: rank tiles present iff the generator feed is live (live=${genLive})`,
    genLive ? rankTiles.length > 0 : rankTiles.length === 0);
  t('signals: no "overall rank #undefined" tile (shipped broken until 2026-08-10)',
    rankTiles.every(x => !/undefined|NaN|null/.test(x.k)));
  t('signals: every tile rank is a number or the unranked marker',
    rankTiles.every(x => /^#\d+$/.test(x.shown) || x.shown === '-'));
  t('signals: a live tile cross-checks against a table row',
    !genLive || rankTiles.some(x => x.tableRank !== null));
  t('signals: tile rank agrees with the table Rank column',
    rankTiles.every(x => x.tableRank === null ||
      (x.shown === '#' + x.tableRank) ||
      (x.shown === '-' && (x.tableRank === '-' || x.tableRank === '·'))));

  // ZSCORE filter -> min auto-drops to 0, book z rows show their research stats.
  // The walk-through only exists when the dropdown carries the option (see the
  // iff check above) - selecting a missing option is a hard playwright timeout
  // that killed the whole suite on 08-14, so the zero-z-day skip is explicit.
  if (!stratOpts.includes('ZSCORE')) {
    t('ZSCORE filter walk-through skipped - zero-z day, dropdown correctly omits it',
      !dropExpect.z);
  } else {
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
  }

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
  /* ---- Unranked rows must say why (2026-08-18) --------------------------
     Book rows are exempt from the min-trades filter, so they render on far
     less evidence than the ranking floor - and then took a bare "-" in the
     Rank cell. On 08/18 CELH GAPW_RSI14 sat at the TOP of the Strength sort
     with 1.963 on 16 trades (bigger than the actual #1, SHOP at 1.253),
     unranked and unexplained, and the owner reasonably asked why a weaker
     row was beating it. A blank Rank beside the biggest number on the page
     is only honest if the row can say what is missing. Assert the behavior,
     not today's tickers: EVERY unranked row carries a reason, and no ranked
     row carries one. */
  const rankCells = await page.evaluate(() => {
    return [...document.querySelectorAll('#signals-table tr')]
      .filter(r => r.querySelector('td'))
      .map(r => {
        const c = [...r.querySelectorAll('td')];
        const td = c[1];
        const why = td.querySelector('.small');
        const bare = td.cloneNode(true);
        bare.querySelectorAll('.small').forEach(n => n.remove());
        return { sym: c[0].textContent.trim().split(/\s/)[0],
                 rank: bare.textContent.trim(),
                 why: why ? why.textContent.trim() : '',
                 strength: c[7].textContent.trim(),
                 n: c[11].textContent.trim() };
      });
  });
  const unranked = rankCells.filter(x => x.rank === '-');
  const numbered = rankCells.filter(x => /^\d+$/.test(x.rank));
  t('signals: table renders both ranked and unranked rows',
    rankCells.length > 0 && numbered.length > 0);
  t('signals: every unranked row states why it is unranked',
    unranked.every(x => x.why.length > 0));
  t('signals: no ranked row carries an unranked reason',
    numbered.every(x => x.why === ''));
  /* The specific trap: the row at the top of the Strength sort is frequently
     the thinnest one, because n/(n+10) discounts a small sample only weakly.
     If the strongest row is unranked, its reason must name the sample. */
  const topByStrength = rankCells
    .filter(x => x.strength && !isNaN(parseFloat(x.strength)))
    .sort((a, b) => parseFloat(b.strength) - parseFloat(a.strength))[0];
  t(`signals: top-Strength row is ranked or explains itself (${topByStrength ?
      topByStrength.sym + ' ' + topByStrength.strength + ' on n=' + topByStrength.n : 'none'})`,
    !topByStrength || topByStrength.rank !== '-' || topByStrength.why.length > 0);
  /* Changing the floor re-ranks the table but NOT the pinned Top-4 card, so
     the page must say the two lists have stopped agreeing. */
  await page.evaluate(() => { document.getElementById('s-minn').value = '10';
    document.getElementById('s-apply').click(); });
  await page.waitForTimeout(300);
  const offFloor = await page.evaluate(() => document.getElementById('s-count').innerText);
  t('signals: a non-standard min-trades floor is disclosed against the Top-4 card',
    /Top-4 buys card/.test(offFloor));
  await page.evaluate(() => { document.getElementById('s-minn').value = '30';
    document.getElementById('s-apply').click(); });
  await page.waitForTimeout(300);
  const onFloor = await page.evaluate(() => document.getElementById('s-count').innerText);
  t('signals: no disclaimer at the standard floor', !/Top-4 buys card/.test(onFloor));

  /* ---- AUDIT 2026-08-18 regressions ------------------------------------
     Each of these is a bug that was live on the 08/18 build. Assert the
     BEHAVIOR, not today's tickers, so ordinary data movement cannot make them
     red and get them deleted. */

  // F1. The Today card had NO evidence gate on book rows: its only
  // recommendation that day was ST/ZSCORE at $6,667 on a six-trade record,
  // while the Signals tab printed Rank "-" for the same row and the mailer
  // dropped it. Nothing sized may sit below the evidence floor.
  const todayGate = await page.evaluate(() => {
    const T = (typeof TODAY_BUYS !== 'undefined' && TODAY_BUYS) || { act: [] };
    const bad = (T.act || []).filter(b =>
      b.n == null || b.avg == null || b.avg <= 0 || b.n < BOOK_MIN_N);
    const txt = document.getElementById('today-body').innerText;
    return { bad: bad.map(b => `${b.sym}/${b.book} n=${b.n} avg=${b.avg}`),
             sized: /Buy ~\$/.test(txt),
             demotedLabelled: [...document.querySelectorAll('#today-body .trow')]
               .filter(r => /NOT A BUY/.test(r.innerText))
               .every(r => r.innerText.split('NOT A BUY')[1].trim().length > 3) };
  });
  t(`today: no sized buy below the evidence floor (${todayGate.bad.join('; ') || 'none'})`,
    todayGate.bad.length === 0);
  t('today: every demoted row states why it is not a buy', todayGate.demotedLabelled);

  // F2. ZFACTOR is read from the blob specifically so it is not hardcoded, and
  // nine strings hardcoded it anyway - two rendering "x0.71" in the same paint
  // as an interpolated "x0.87". No visible string may assert a factor that is
  // not the live one, except the research rows that quote both by name.
  const zf = await page.evaluate(() => {
    const f = String(ZFACTOR);
    const bad = [];
    for (const tab of TABS.map(t2 => t2[0])) {
      const el2 = document.getElementById(tab + '-body');
      if (!el2) continue;
      for (const line of el2.innerText.split('\n')) {
        // Only EXECUTION-BASIS claims, not every decimal on the page: the
        // phrase has to be about keeping/executing a fraction per trade.
        if (!/executable|keep-rate|keeps ~?x?0?\.|per trade/i.test(line)) continue;
        const m = line.match(/x\s?0\.\d{2}/gi);
        if (!m) continue;
        // The x41 and x43 rows quote BOTH bases by name on purpose - they are
        // records of what was measured, not claims about the current basis.
        // Exempt ONLY lines that quote BOTH bases - the x41/x43 research rows
        // are records of what was measured. The old test was /x41|x43|vs x0.71/,
        // which exempted any line MENTIONING x43 - and since ZFACTOR's
        // provenance IS x43, every paragraph about the execution basis names
        // it, so the check was disabled exactly where it mattered. Proven
        // 2026-08-18: hardcoding "~x0.71" into the Guide's keep-rate sentence
        // still returned PASS.
        if (/0\.71/.test(line) && /0\.87/.test(line)) continue;
        for (const hit of m) {
          const v = (hit.match(/0\.\d{2}/) || [])[0];
          if (v && v !== f) bad.push(tab + ': ' + line.trim().slice(0, 100));
        }
      }
    }
    return { f, bad: [...new Set(bad)] };
  });
  t(`no stale execution-factor literal anywhere (ZFACTOR=${zf.f})`,
    zf.bad.length === 0);
  if (zf.bad.length) zf.bad.forEach(b => console.log('    ' + b));

  /* F3. The Today card's wall-clock suppression had ZERO coverage: flipping
     pageStale in either direction left the suite at 112 PASS / exit 0. Both
     directions are asserted here, driven by a shifted clock rather than by
     editing the page, so what is tested is the real code path. The sizing
     assertion above is written `!/Buy ~\$/.test(...) || ...`, which passes
     VACUOUSLY once the list is suppressed - so without this, suppression
     silently disarms that check too. */
  const staleProbe = async (offsetDays) => {
    const p2 = await browser.newPage();
    if (offsetDays) {
      await p2.addInitScript(off => {
        const R = Date, shift = off * 86400000;
        Date = class extends R {
          constructor(...a) { if (a.length) super(...a); else super(R.now() + shift); }
          static now() { return R.now() + shift; }
        };
      }, offsetDays);
    }
    await p2.goto(PAGE);
    await p2.waitForTimeout(700);
    await p2.evaluate(() => document.querySelector('[data-tab="today"]').click());
    await p2.waitForTimeout(250);
    const txt = await p2.evaluate(() => document.getElementById('today-body').innerText);
    await p2.close();
    return { banner: /buy list suppressed/i.test(txt),
             sized: /Buy ~\$/.test(txt),
             sells: /Sell/.test(txt) };
  };
  const fresh = await staleProbe(0);
  const aged = await staleProbe(9);
  t('today: fresh page shows no staleness banner', !fresh.banner);
  t('today: a 9-day-old page suppresses the buy list', aged.banner && !aged.sized);
  t('today: suppression still shows sells (an open position must be actionable)',
    !fresh.sells || aged.sells);

  // F8. The stale-feed killbox fired on a FULLY FRESH feed once demote_stale
  // stamped individual symbols PASS-STALE. A gate that fires daily is a gate
  // nobody reads, and this one exists to catch a TROW-class failure.
  const staleGate = await page.evaluate(() => {
    const live = (typeof TRACK !== 'undefined' && TRACK && TRACK.as_of) || '';
    const sigbar = ((typeof SIGNALS !== 'undefined' && SIGNALS.signals) || [])
      .reduce((m, x) => (x.as_of || '') > m ? (x.as_of || '') : m, '');
    return { feedBehind: !!(live && sigbar && sigbar < live),
             banner: /Signal feed is stale/.test(document.body.innerText) };
  });
  t(`signals: stale killbox fires iff the FEED is behind (behind=${staleGate.feedBehind})`,
    staleGate.banner === staleGate.feedBehind);

  // F10. Two harnesses emit two different "zero losses" sentinels (99, 999).
  // Neither is a profit factor; the largest genuine PF in this data is 69.98.
  const pfRaw = await page.evaluate(() => {
    const hits = [];
    for (const tab of TABS.map(t2 => t2[0])) {
      const el2 = document.getElementById(tab + '-body');
      if (!el2) continue;
      el2.querySelectorAll('details').forEach(d => d.open = true);
      // a sentinel that reached a CELL renders as its own td text
      el2.querySelectorAll('td').forEach(td => {
        const v = td.textContent.trim();
        if (v === '999' || v === '999.0' || v === '99.0' || v === '99') hits.push(tab + ':' + v);
      });
    }
    return [...new Set(hits)];
  });
  t(`no raw PF sentinel renders as a number (${pfRaw.join(', ') || 'none'})`,
    pfRaw.length === 0);

  /* ---- MATURITY BIAS (audit round 3, 2026-08-18) ----------------------
     The exit rules fire on strength, so a winner closes in 1-2 bars while a
     loser's only exit is the 10-bar time stop. For the first ten sessions of
     any position's life the closed set is therefore the winning half BY
     CONSTRUCTION. Publishing it alone read +1.66%/trade program-wide when
     marking every position gave -0.31%; GAPW_RSI14 advertised 94.3% win /
     +3.44%/trade with 30 of its 31 open positions underwater. The open book
     was carried at COST, so that drawdown appeared nowhere on the site.
     These assert the SHAPE - a book with open positions must publish its mark
     - so they survive data movement and go red only if the marking is lost. */
  await page.evaluate(() => document.querySelector('[data-tab="positions"]').click());
  await page.waitForTimeout(500);
  const mark = await page.evaluate(() => {
    const S = (typeof SHADOW !== 'undefined' && SHADOW) || {};
    const st = S.stats || {}, P = S.portfolio || {};
    const missing = Object.entries(st)
      .filter(([, v]) => (v.open || 0) > 0 && (v.mark_avg === undefined || v.mark_avg === null))
      .map(([b]) => b);
    const txt = document.getElementById('positions-body').innerText;
    return {
      missing,
      booksWithOpen: Object.values(st).filter(v => (v.open || 0) > 0).length,
      hasMarketEquity: P.equity_at_market !== undefined && P.equity_at_market !== null,
      equityShown: (P.equity_at_market != null)
        ? txt.includes(Math.round(P.equity_at_market).toLocaleString()) : false,
      costOnlyClaim: /open positions carried at cost, so this moves only as trades close/.test(txt),
      explains: /closed set the winning half by construction|winning half by construction/i.test(txt),
    };
  });
  t(`positions: every book with open positions publishes a mark (${mark.missing.join(', ') || 'all marked'})`,
    mark.missing.length === 0);
  t('positions: the account carries a marked-to-market equity, not only cost',
    mark.hasMarketEquity);
  t('positions: the marked equity is the figure actually rendered',
    !mark.hasMarketEquity || mark.equityShown);
  t('positions: the old cost-basis-only claim is gone', !mark.costOnlyClaim);
  t('positions: the page explains why the closed set skews to winners', mark.explains);

  /* ---- VETTED forward-check card (2026-08-19) ---------------------------
     Confirmed by causal refit: selected/rejected arms are statistically
     indistinguishable in the era the selection never saw, while the published
     badge (fit in-sample) reads ~1.5-1.6x higher. Assert the card exists and
     states a real per-strategy comparison, not that any particular number
     holds - the underlying data moves as SCAN refreshes. */
  await page.evaluate(() => document.querySelector('[data-tab="guide"]').click());
  await page.waitForTimeout(400);
  const vetCheck = await page.evaluate(() => {
    const t = document.getElementById('guide-body').innerText;
    const i = t.indexOf('Does the VETTED badge predict forward returns');
    if (i < 0) return { present: false };
    const rows = [...document.querySelectorAll('#guide-body table tr')]
      .map(r => [...r.querySelectorAll('td')].map(c => c.textContent.trim()))
      .filter(c => c.length === 8);
    return { present: true, rowCount: rows.length,
             allNumeric: rows.every(r => r.slice(1).every(v => v === '-' || /^[+-]?\d/.test(v))) };
  });
  t('guide: the VETTED forward-check card is present', vetCheck.present);
  t('guide: it reports at least one strategy row', !vetCheck.present || vetCheck.rowCount > 0);
  t('guide: every row is numeric, not a rendering leak', !vetCheck.present || vetCheck.allNumeric);

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
  const hbStale = await page.evaluate(() =>
    (typeof HEALTH !== 'undefined' && HEALTH) ? !!HEALTH.signals_stale : false);
  t('header: signals_stale echo iff HEALTH stamps it',
    hbStale ? pline.includes('generator feed stale')
            : !pline.includes('generator feed stale'));
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

  if (errors.length) process.exitCode = 1;
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'NO PAGE ERRORS');
  await browser.close();
})();
