// Documentation artwork only. Never reads private fixtures or changes reports.
// See SHOWCASE.md for the isolated tooling setup and reproduction command.
import { createRequire } from 'node:module';
import { readFile, mkdir, mkdtemp, rm, copyFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const assets = dirname(fileURLToPath(import.meta.url));
const root = resolve(assets, '../..');
if (!process.env.SHOWCASE_TOOLS) throw new Error('Set SHOWCASE_TOOLS as documented in SHOWCASE.md');
const require = createRequire(resolve(process.env.SHOWCASE_TOOLS, 'package.json'));
const { chromium } = require('playwright-core');
const output = process.env.SHOWCASE_OUTPUT || join(root, '.github/assets');
const frames = await mkdtemp(join(tmpdir(), 'sdr-showcase-'));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.SHOWCASE_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: true,
});
try {
  const page = await browser.newPage({ viewport: { width: 1120, height: 720 }, deviceScaleFactor: 1 });
  // Block all network access: every pixel comes from this repository and local fonts.
  await page.route('**/*', route => route.abort());
  const specifications = [
    { file: 'grade-cja-clean.html', selectors: ['h1', '.meta-strip', '#categories'],
      kicker: '01 / Verify what’s working', title: 'Confidence,<br>with evidence.',
      description: 'Recognize a healthy implementation. See the grade and the category scores behind it.',
      proof: 'CJA · 40 components evaluated<br>A / 100% · strict@2.0', seconds: 4.5 },
    { file: 'grade-cja-messy.html', selectors: ['#categories'],
      kicker: '02 / Find the weak spots', title: 'One grade.<br>The whole<br>picture.',
      description: 'Naming looks good. Governance needs attention. Focus the conversation where it matters.',
      proof: 'CJA · 487 components evaluated<br>Separate diagnostic example', seconds: 4.5 },
    { file: 'grade-cja-messy.html', selectors: ['#finding-calc-014'],
      kicker: '03 / Turn findings into action', title: 'Know exactly<br>what to fix.',
      description: 'Trace a finding to affected components, then follow a concrete remediation.',
      proof: 'CALC-014 · High severity<br>Evidence → components → next step', seconds: 8 },
    { file: 'grade-aa-clean.html', selectors: ['h1', '.meta-strip', '#categories'],
      kicker: '04 / Grade Adobe Analytics', title: 'Clarity.<br>Across<br>platforms.',
      description: 'Grade Adobe Analytics and CJA snapshots. Share the HTML report; automate with JSON.',
      proof: 'AA · 19 components evaluated<br>A / 100% · strict@2.0', seconds: 4.5 },
  ];
  const scenes = [];
  for (const spec of specifications) {
    await page.setContent(await readFile(join(root, 'examples', spec.file), 'utf8'));
    scenes.push({ ...spec, ...await page.evaluate(selectors => ({
      css: document.querySelector('style').textContent,
      html: selectors.map(selector => {
        const element = document.querySelector(selector);
        if (!element) throw new Error(`Missing report excerpt: ${selector}`);
        return element.outerHTML;
      }).join('\n'),
    }), spec.selectors) });
  }
  await page.setContent(await readFile(join(assets, 'showcase.html'), 'utf8'));
  await page.evaluate(scenes => {
    for (const scene of scenes) {
      const element = document.createElement('div');
      element.className = 'scene';
      element.innerHTML = `<div class="story"><div class="kicker">${scene.kicker}</div><h1>${scene.title}</h1><p class="description">${scene.description}</p><div class="proof">${scene.proof}</div></div><div class="window"><div class="window-bar"><i class="dot"></i><i class="dot"></i><i class="dot"></i><span class="filename">${scene.file} · excerpt</span></div><div class="excerpt"></div></div>`;
      // Isolate the unchanged report stylesheet from the editorial frame.
      const shadow = element.querySelector('.excerpt').attachShadow({ mode: 'open' });
      shadow.innerHTML = `<style>${scene.css.replaceAll(':root', ':host')}
        :host { display:block; color:var(--sdr-text-primary); background:var(--sdr-surface-page);
          font:16px/1.55 "Charter","Iowan Old Style","Source Serif Pro",Georgia,serif; }
      </style>${scene.html}`;
      document.querySelector('#scenes').append(element);
    }
  }, scenes);
  const fps = 8;
  const totalFrames = scenes.reduce((total, scene) => total + scene.seconds * fps, 0);
  let frame = 0;
  for (let index = 0; index < scenes.length; index++) {
    for (let tick = 0; tick < scenes[index].seconds * fps; tick++, frame++) {
      await page.evaluate(({ index, tick, frame, totalFrames }) => {
        document.querySelectorAll('.scene').forEach((element, i) => {
          element.style.visibility = i === index ? 'visible' : 'hidden';
          // A small entrance movement; long still holds keep the reports readable.
          element.style.transform = `translateY(${tick < 3 ? (3 - tick) * 2 : 0}px)`;
        });
        document.querySelectorAll('.steps span').forEach((element, i) => element.classList.toggle('active', i === index));
        document.querySelector('.progress').style.transform = `scaleX(${(frame + 1) / totalFrames})`;
      }, { index, tick, frame, totalFrames });
      await page.screenshot({ path: join(frames, `${String(frame).padStart(4, '0')}.png`) });
      if (tick === 3) await page.screenshot({ path: join(output, `showcase-scene-${index + 1}.png`) });
    }
  }
  await copyFile(join(output, 'showcase-scene-1.png'), join(output, 'grader-showcase.png'));
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-framerate', String(fps),
    '-i', join(frames, '%04d.png'), '-filter_complex',
    '[0:v]split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=none:diff_mode=rectangle',
    '-loop', '0', join(output, 'grader-showcase.gif')], { stdio: 'inherit' });
  console.log(`Rendered ${totalFrames} frames / ${totalFrames / fps}s to ${output}`);
} finally {
  await browser.close();
  await rm(frames, { recursive: true, force: true });
}
