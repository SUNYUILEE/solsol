'use strict';
// Do not replace a control when an asynchronous validation response arrives.
(() => {
 const body = $('settingsBody'), panel = body.closest('.settings');
 const previous = renderSettings;
 let renderedContext = null, pending = false, rendering = false, userEvent = false, eventEpoch = 0, renderedDraft = null, renderedSelection = null, renderedResourceStructure = null;
 const positions = new Map();
 const context = () => `${draft.sensor}/${setting}`;
 const focused = () => body.contains(document.activeElement);
 const controls = () => [...body.querySelectorAll('input,select,textarea,button')];
 const identity = el => el?.id || el?.dataset.field || (el?.closest('label')?.textContent || el?.getAttribute('aria-label') || el?.textContent || '').trim();
 function refresh() {
  if (!draft) return;
  const key = context(), same = key === renderedContext;
  const currentSelection = typeof selection === 'function' ? selection() : null;
  const sameDraft = draft === renderedDraft && currentSelection === renderedSelection;
  const resource = currentSelection?.resource_contract;
  const resourceStructure = JSON.stringify(resource ? [resource.budget?.mode,Object.entries(resource.sensor_counts||{}).map(([id,c])=>[id,c.mode,Object.keys(c).sort()]),Object.keys(resource.cost?.sensor_unit_costs||{})] : null);
  if (rendering) return;
  if (same && sameDraft && focused() && !userEvent && resourceStructure === renderedResourceStructure) {
   pending = true;
   const confirmed = $('confirmedExecution');
   if (confirmed) confirmed.style.visibility = 'hidden';
   return;
  }
  const active = focused() ? document.activeElement : null;
  const activeKey = identity(active), y = active?.getBoundingClientRect().top;
  const caretRange = active && ['text','search','url','tel','password'].includes(active.type)
   ? [active.selectionStart, active.selectionEnd] : null;
  const opened = new Set([...body.querySelectorAll('details[open]')].map(el => el.id || el.querySelector('summary')?.textContent));
  if (renderedContext) positions.set(renderedContext, body.scrollTop);
  const scroll = same ? body.scrollTop : positions.get(key) || 0;
  rendering = true;
  try {
   previous();
   if (same) for (const el of body.querySelectorAll('details'))
    el.open = opened.has(el.id || el.querySelector('summary')?.textContent);
   body.scrollTop = scroll;
   if (same && active) {
    const replacement = controls().find(el => identity(el) === activeKey && el.tagName === active.tagName);
    if (replacement) {
     replacement.focus({preventScroll:true});
     if (caretRange) replacement.setSelectionRange(...caretRange);
     body.scrollTop += replacement.getBoundingClientRect().top - y;
    }
   }
   renderedContext = key;
   renderedDraft = draft;
   renderedSelection = currentSelection;
   renderedResourceStructure = resourceStructure;
   pending = false;
  } finally { rendering = false; }
 }
 // Dependent fields can change synchronously; background redraws wait for blur.
 for (const type of ['input','change','click']) body.addEventListener(type, event => {
  const target = event.target;
  // Numeric/text keystrokes and their blur change are never structural edits.
  // Only explicit dropdown, checkbox, or button actions may rebuild this view.
  userEvent = type !== 'input' && !!target.closest('select,button,input[type=checkbox],input[type=radio]');
  const epoch = ++eventEpoch;
  setTimeout(() => { if (epoch === eventEpoch) userEvent = false; }, 0);
 }, true);
 body.addEventListener('focusout', () => setTimeout(() => {
  if (!rendering && pending && !focused()) refresh();
 }, 0));
 renderSettings = refresh;
 const expand = document.createElement('button');
 expand.id = 'expandSettings';
 let wide = false;
 try { wide = localStorage.getItem('solsol.settings.wide') === 'true'; } catch (_) {}
 function width() {
  document.body.classList.toggle('settingsWide', wide);
  expand.textContent = wide ? '기본 너비' : '넓게 보기';
  expand.setAttribute('aria-pressed', String(wide));
 }
 expand.onclick = () => { wide = !wide; width(); try { localStorage.setItem('solsol.settings.wide', String(wide)); } catch (_) {} };
 panel.querySelector('.panelHead').append(expand); width();
 const explanation = document.createElement('details');
 explanation.id = 'settingsExplanation';
 const summary = document.createElement('summary');
 const contents = document.createElement('div'); contents.id = 'settingsExplanationBody';
 const foot = panel.querySelector('.settingFoot');
 for (const child of [...foot.children]) if (child.id !== 'copyRun') contents.append(child);
 explanation.append(summary, contents); foot.prepend(explanation);
 try { explanation.open = localStorage.getItem('solsol.settings.explanation') === 'true'; } catch (_) {}
 function explanationLabel() { summary.textContent = explanation.open ? '조건 설명 숨기기' : '조건 설명 보기'; }
 explanation.addEventListener('toggle', () => { explanationLabel(); try { localStorage.setItem('solsol.settings.explanation', String(explanation.open)); } catch (_) {} });
 explanationLabel();
 refresh();
})();
