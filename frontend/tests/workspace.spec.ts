import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const fixture = 'id: https://fastonto.example/test\nname: sample\ntitle: 测试模型\n';
const report = {
  valid: true, name: 'sample', title: '测试模型', sha256: 'a'.repeat(64), enum_count: 0,
  classes: [{name: 'Product', title: '产品', description: '用于测试的模型', uri: `https://example.test/${'long-uri-'.repeat(60)}`, slots: [{name: 'id', title: '标识', range: 'string', required: true, multivalued: false, identifier: true}, {name: 'name', title: '名称', range: 'string', required: true, multivalued: false, identifier: false}, {name: 'category', title: '分类', range: 'string', required: false, multivalued: false, identifier: false}, {name: 'price', title: '价格', range: 'decimal', required: false, multivalued: false, identifier: false}, {name: 'note', title: '备注', range: 'string', required: false, multivalued: false, identifier: false}]}],
  relationships: [], warnings: ['结构校验不代表实例校验。'],
};
const sources = ['PRODUCTS', 'CUSTOMERS'].map(name => ({name, title: name === 'PRODUCTS' ? '产品' : '客户', owner: 'SH', columns: ['ID', 'NAME'], identity: '源主键'}));

async function fixtureApp(page: Page, options: { delayValidation?: number; saveFailure?: boolean; sourceFailure?: boolean; sourceEmpty?: boolean; malformedTheme?: boolean; dbConfigured?: boolean; importDelay?: number; importFailure?: boolean; importEmpty?: boolean; legacyGovernanceCatalog?: boolean } = {}) {
  if (options.malformedTheme) await page.addInitScript(() => localStorage.setItem('fastonto.theme.v1', '{broken-json'));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/')) {
      let body: unknown, status = 200;
      if (url.pathname === '/api/auth/me') body = {user: {id: 'test-user', username: 'admin', must_change_password: false}, csrf_token: 'test-csrf', insecure_http: true};
      else if (url.pathname === '/api/system') body = {database_configured: options.dbConfigured ?? false, mode: 'authenticated', version: '0.2.0'};
      else if (url.pathname === '/api/models/template') body = {source: fixture + (url.searchParams.has('name') ? `# template: ${url.searchParams.get('name')}\n` : ''), saved: false};
      else if (url.pathname === '/api/models/import') {
        if (options.importDelay) await new Promise(r => setTimeout(r, options.importDelay));
        const submitted = route.request().postDataJSON();
        status = options.importFailure ? 422 : 200;
        body = options.importFailure ? {detail: '文件损坏，请重新上传。'} : submitted.filename.endsWith('.yaml')
          ? {kind: 'yaml', source: fixture + '# imported yaml\n'}
          : {kind: 'document', filename: submitted.filename, warnings: ['本地规则提取，不调用外部 AI。'], classes: options.importEmpty ? [] : [{name: 'Standard', title: '标准', evidence: 'Sheet1 第 1 行', fields: [{name: 'issuedBy', title: '发布机构', range: 'string', required: false, multivalued: false, description: '', evidence: 'Sheet1 第 1 行第 2 列'}]}]};
      } else if (url.pathname === '/api/models/draft') body = {source: fixture + '# generated draft\n'};
      else if (url.pathname.startsWith('/api/models/export/')) body = {content: url.pathname.endsWith('jsonschema') ? '{}' : '@prefix demo: <https://example.org/> .'};
      else if (url.pathname === '/api/models' && route.request().method() === 'GET') body = {items: [{id: '00000000-0000-0000-0000-000000000001', title: '已保存模型', revision: 1}]};
      else if (url.pathname === '/api/llm-models') body = {items: [{id: '00000000-0000-0000-0000-000000000010', title: '测试 LLM', model_name: 'test-model', enabled: true, is_default: true}]};
      else if (url.pathname === '/api/models' && route.request().method() === 'POST') {
        status = options.saveFailure ? 409 : 200;
        body = options.saveFailure ? {detail: '模型版本已变化，请保留草稿。'} : {id: '00000000-0000-0000-0000-000000000001', title: '测试模型', revision: 1};
      } else if (url.pathname === '/api/governance/catalog') {
        body = options.legacyGovernanceCatalog ? {domains: []} : {domains: [], ontologies: [], mappings: [], entity_links: [], assets: [], notice: ''};
      } else if (url.pathname === '/api/models/validate') {
        if (options.delayValidation) await new Promise(r => setTimeout(r, options.delayValidation));
        const submitted = route.request().postDataJSON() as {source: string};
        status = submitted.source === 'invalid' ? 422 : 200;
        body = status === 422 ? {detail: '模型格式不正确。'} : report;
      } else if (url.pathname.startsWith('/api/models/0000')) body = {id: '00000000-0000-0000-0000-000000000001', title: '已保存模型', revision: 1, source: fixture + '# saved version\n'};
      else if (url.pathname === '/api/sources') body = {items: sources};
      else if (url.pathname.includes('/preview')) {
        const source = url.pathname.split('/')[3];
        if (source === 'PRODUCTS') await new Promise(r => setTimeout(r, 150));
        status = options.sourceFailure ? 503 : 200;
        body = options.sourceFailure ? {detail: '请配置数据库连接。'} : {source, columns: ['ID', 'NAME'], rows: options.sourceEmpty ? [] : [['1', source === 'PRODUCTS' ? '便携式足球门' : '客户样例']], offset: 0, limit: 20, has_more: false, notice: '源数据不落副本。'};
      } else {status = 503; body = {detail: '请配置数据库连接。'};}
      await route.fulfill({status, contentType: 'application/json', body: JSON.stringify(body)}); return;
    }
    const asset = url.pathname.startsWith('/assets/') || url.pathname === '/theme.js' ? path.join(process.cwd(), 'dist', url.pathname) : path.join(process.cwd(), 'dist/index.html');
    const contentType = asset.endsWith('.js') ? 'application/javascript' : asset.endsWith('.css') ? 'text/css' : 'text/html';
    await route.fulfill({contentType, body: await fs.readFile(asset)});
  });
  await page.goto('/models');
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
}

for (const viewport of [{width: 1440, height: 1000}, {width: 375, height: 812}, {width: 320, height: 740}, {width: 812, height: 375}]) {
  for (const theme of ['dark', 'light']) {
    test(`layout ${viewport.width}x${viewport.height} ${theme}`, async ({page}) => {
      await page.setViewportSize(viewport);
      await fixtureApp(page);
      if (theme === 'light') await page.getByRole('button', {name: '切换浅色主题'}).click();
      await page.getByRole('button', {name: '校验模型', exact: true}).click();
      await expect(page.getByText('该快照已通过模型结构校验。')).toBeVisible();
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
      const save = page.getByRole('button', {name: '保存版本'});
      await save.scrollIntoViewIfNeeded(); await expect(save).toBeInViewport();
      if (viewport.width === 1440 || viewport.width === 375) await page.screenshot({path: `test-results/model-${viewport.width}-${theme}.png`, fullPage: true});
      await page.getByRole('link', {name: '业务数据源'}).click();
      await expect(page.getByText('便携式足球门')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    });
  }
}

test('late validation does not replace edited draft and is marked stale', async ({page}) => {
  await fixtureApp(page, {delayValidation: 400});
  await page.getByRole('button', {name: '校验模型', exact: true}).click();
  const changed = fixture + '# newer edit\n';
  await page.getByLabel('LinkML 模型源码').fill(changed);
  await expect(page.getByText('草稿已变化，下方结果来自旧快照，请重新校验。')).toBeVisible();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(changed);
});

test('validated model exposes the visual ontology canvas', async ({page}) => {
  await fixtureApp(page);
  await page.getByRole('button', {name: '校验模型', exact: true}).click();
  await expect(page.getByLabel('本体关系图')).toBeVisible();
  await expect(page.getByRole('button', {name: '拖拽 产品'})).toBeVisible();
  await expect(page.getByText('当前模型没有对象关系；可先在 LinkML 中定义类之间的属性关系。')).toBeVisible();
  await page.getByRole('button', {name: '展开其余 1 个属性'}).click();
  await expect(page.locator('.ontology-node').getByText('备注', {exact: true})).toBeVisible();
  await expect(page.getByRole('button', {name: '恢复默认'})).toBeVisible();
});

test('save conflict keeps draft', async ({page}) => {
  await fixtureApp(page, {saveFailure: true});
  await page.getByRole('button', {name: '保存版本'}).click();
  await expect(page.getByRole('alert')).toContainText('模型版本已变化');
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
});

test('route navigation preserves unsaved draft', async ({page}) => {
  await fixtureApp(page);
  await page.getByLabel('LinkML 模型源码').fill(fixture + '# unsaved\n');
  await page.getByRole('link', {name: '业务数据源'}).click();
  await page.getByRole('link', {name: '模型工作台'}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture + '# unsaved\n');
});

test('governance remains available when a backend catalog omits newer collections', async ({page}) => {
  await fixtureApp(page, {legacyGovernanceCatalog: true});
  await page.getByRole('link', {name: '业务域治理'}).click();
  await expect(page.getByRole('heading', {name: '业务域与本体'})).toBeVisible();
  await expect(page.getByText('尚无业务域。请先创建例如“销售域”。')).toBeVisible();
  await expect(page.getByText('无法显示')).not.toBeVisible();
});

test('model switch confirmation is cancellable in light mobile theme', async ({page}) => {
  await page.setViewportSize({width: 375, height: 812});
  await fixtureApp(page);
  await page.getByRole('button', {name: '切换浅色主题'}).click();
  await page.getByLabel('已保存的模型').selectOption('00000000-0000-0000-0000-000000000001');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', {name: '保留草稿'}).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
});

test('stale source response cannot replace latest selection', async ({page}) => {
  await fixtureApp(page);
  await page.getByRole('link', {name: '业务数据源'}).click();
  await page.getByRole('button', {name: /客户 SH.CUSTOMERS/}).click();
  await expect(page.getByText('客户样例')).toBeVisible();
  await expect(page.getByText('便携式足球门')).not.toBeVisible();
});

test('source failures expose retry without fake rows', async ({page}) => {
  await fixtureApp(page, {sourceFailure: true, malformedTheme: true});
  await page.getByRole('link', {name: '业务数据源'}).click();
  await expect(page.getByRole('alert')).toContainText('请配置数据库连接');
  await expect(page.getByRole('button', {name: '重试', exact: true})).toBeVisible();
  await expect(page.getByRole('table')).not.toBeVisible();
});

test('empty source preserves navigation and refresh', async ({page}) => {
  await fixtureApp(page, {sourceEmpty: true});
  await page.getByRole('link', {name: '业务数据源'}).click();
  await expect(page.getByText('当前范围没有记录。')).toBeVisible();
  await expect(page.getByRole('button', {name: '下一页'})).toBeDisabled();
  await expect(page.getByRole('button', {name: '刷新源数据'})).toBeEnabled();
});

test('invalid validation keeps source and prior report explicitly stale', async ({page}) => {
  await fixtureApp(page);
  await page.getByRole('button', {name: '校验模型', exact: true}).click();
  await expect(page.getByText('该快照已通过模型结构校验。')).toBeVisible();
  await page.getByLabel('LinkML 模型源码').fill('invalid');
  await page.getByRole('button', {name: '校验模型', exact: true}).click();
  await expect(page.getByRole('alert')).toContainText('模型格式不正确');
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue('invalid');
  await expect(page.getByText('草稿已变化，下方结果来自旧快照，请重新校验。')).toBeVisible();
});

test('escape cancels model switch and returns focus', async ({page}) => {
  await fixtureApp(page);
  await page.getByLabel('已保存的模型').selectOption('00000000-0000-0000-0000-000000000001');
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
});

async function openSaved(page: Page) {
  await page.getByLabel('已保存的模型').selectOption('00000000-0000-0000-0000-000000000001');
  await page.getByRole('button', {name: '放弃草稿并打开'}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture + '# saved version\n');
}

async function chooseFile(page: Page, name = '标准.xlsx') {
  await page.getByLabel('上传模型或业务文档').setInputFiles({name, mimeType: 'application/octet-stream', buffer: Buffer.from('synthetic fixture')});
}

test('new template after opening a model saves with null id and revision zero', async ({page}) => {
  await fixtureApp(page); await openSaved(page);
  await page.getByRole('button', {name: '新建模型', exact: true}).click();
  await page.getByRole('button', {name: '标准与发布机构', exact: true}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture + '# template: standards\n');
  const request = page.waitForRequest(r => r.url().endsWith('/api/models') && r.method() === 'POST');
  await page.getByRole('button', {name: '保存版本'}).click();
  expect((await request).postDataJSON()).toMatchObject({id: null, expected_revision: 0});
});

test('save as uses new id while ordinary save keeps original id', async ({page}) => {
  await fixtureApp(page); await openSaved(page);
  let request = page.waitForRequest(r => r.url().endsWith('/api/models') && r.method() === 'POST');
  await page.getByRole('button', {name: '保存版本'}).click();
  expect((await request).postDataJSON()).toMatchObject({id: '00000000-0000-0000-0000-000000000001', expected_revision: 1});
  await expect(page.getByRole('button', {name: '另存为新模型'})).toBeEnabled();
  request = page.waitForRequest(r => r.url().endsWith('/api/models') && r.method() === 'POST');
  await page.getByRole('button', {name: '另存为新模型'}).click();
  expect((await request).postDataJSON()).toMatchObject({id: null, expected_revision: 0});
});

test('YAML import protects unsaved draft and opens as independent model', async ({page}) => {
  await fixtureApp(page);
  await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page, 'model.yaml');
  await expect(page.getByLabel('YAML 导入预览')).toContainText('# imported yaml');
  await page.getByRole('button', {name: '导入为独立草稿'}).click();
  await page.getByRole('button', {name: '保留草稿', exact: true}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
  await page.getByRole('button', {name: '导入为独立草稿'}).click();
  await page.getByRole('button', {name: '放弃草稿并打开'}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture + '# imported yaml\n');
});

for (const width of [1440, 375, 320]) for (const theme of ['dark', 'light']) {
  test(`document review ${width} ${theme}`, async ({page}) => {
    await page.setViewportSize({width, height: 900});
    await fixtureApp(page);
    if (theme === 'light') await page.getByRole('button', {name: '切换浅色主题'}).click();
    await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page);
    await expect(page.getByRole('heading', {name: '审核候选模型'})).toBeVisible();
    await expect(page.getByRole('button', {name: '生成并打开独立草稿'})).toBeDisabled();
    await page.getByLabel('命名空间 IRI').fill(`https://example.org/${'long-namespace-'.repeat(45)}/`);
    await page.getByRole('button', {name: '添加类', exact: true}).click();
    await page.getByLabel('类技术标识', {exact: true}).nth(1).fill('Organization');
    await page.getByLabel('类名称', {exact: true}).nth(1).fill('机构');
    await page.getByLabel('类型或目标类').selectOption('Organization');
    await page.getByLabel('我已审核候选类、属性及关系；生成结果仍需业务验证').check();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBeTruthy();
    if (width === 1440 || width === 375) await page.screenshot({path: `test-results/import-${width}-${theme}.png`, fullPage: true});
    const request = page.waitForRequest(r => r.url().endsWith('/api/models/draft'));
    await page.getByRole('button', {name: '生成并打开独立草稿'}).click();
    expect((await request).postDataJSON().classes[0].fields[0].range).toBe('Organization');
    await page.getByRole('button', {name: '放弃草稿并打开'}).click();
    await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture + '# generated draft\n');
  });
}

test('candidate edits survive navigation and require confirmation again', async ({page}) => {
  await fixtureApp(page);
  await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page, 'x.md');
  await page.getByLabel('模型中文名称').fill('我的标准模型');
  await page.getByLabel('我已审核候选类、属性及关系；生成结果仍需业务验证').check();
  await page.getByLabel('属性名称', {exact: true}).fill('审核后的属性');
  await expect(page.getByRole('button', {name: '生成并打开独立草稿'})).toBeDisabled();
  await page.getByRole('link', {name: '业务数据源'}).click();
  await page.getByRole('link', {name: '模型工作台'}).click();
  await expect(page.getByLabel('模型中文名称')).toHaveValue('我的标准模型');
  await expect(page.getByLabel('属性名称', {exact: true})).toHaveValue('审核后的属性');
});

test('cancelled slow import cannot replace a later template', async ({page}) => {
  await fixtureApp(page, {importDelay: 1000});
  await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page);
  await expect(page.getByText('正在处理，请稍候… 原模型不会被自动覆盖。')).toBeVisible();
  await page.getByRole('button', {name: '关闭向导'}).click();
  await page.getByRole('button', {name: '丢弃候选并关闭'}).click();
  await page.getByRole('button', {name: '新建模型', exact: true}).click();
  await page.getByRole('button', {name: '空白模型骨架'}).click();
  await page.getByRole('button', {name: '放弃草稿并打开'}).click();
  await page.waitForTimeout(1100);
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture + '# template: blank\n');
  await expect(page.getByRole('heading', {name: '审核候选模型'})).not.toBeVisible();
});

test('empty candidates and malformed upload preserve original source', async ({page}) => {
  await fixtureApp(page, {importEmpty: true});
  await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page, 'plain.txt');
  await expect(page.getByText('没有候选类。可手动添加类和属性，或将文件整理为数据字典后重试。')).toBeVisible();
  await expect(page.getByRole('button', {name: '生成并打开独立草稿'})).toBeDisabled();
  await chooseFile(page, 'old.doc');
  await expect(page.getByRole('alert')).toContainText('旧版 XLS/DOC 请先转换');
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
});

test('server import error leaves retry enabled and no fabricated candidates', async ({page}) => {
  await fixtureApp(page, {importFailure: true});
  await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page);
  await expect(page.getByRole('alert')).toContainText('文件损坏');
  await expect(page.getByLabel('上传模型或业务文档')).toBeEnabled();
  await expect(page.getByRole('heading', {name: '审核候选模型'})).not.toBeVisible();
});

for (const format of ['OWL', 'SHACL', 'JSON Schema']) test(`downloads ${format}`, async ({page}) => {
  await fixtureApp(page);
  const download = page.waitForEvent('download');
  await page.getByRole('button', {name: format, exact: true}).click();
  expect((await download).suggestedFilename()).toBe(format === 'JSON Schema' ? 'schema.json' : `${format.toLowerCase()}.ttl`);
});

test('late template response checks latest edits before replacing source', async ({page}) => {
  await fixtureApp(page); await openSaved(page);
  await page.route('**/api/models/template?name=blank', async route => {
    await new Promise(r => setTimeout(r, 600));
    await route.fulfill({json: {source: fixture + '# delayed template\n'}});
  });
  await page.getByRole('button', {name: '新建模型', exact: true}).click();
  await page.getByRole('button', {name: '空白模型骨架'}).click();
  const edited = fixture + '# saved version\n# newest edit\n';
  await page.getByLabel('LinkML 模型源码').fill(edited);
  await expect(page.getByRole('dialog', {name: '创建独立草稿？'})).toBeVisible();
  await page.getByRole('button', {name: '保留草稿', exact: true}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(edited);
});

test('late generation on another route waits for model page before confirmation', async ({page}) => {
  await fixtureApp(page);
  await page.route('**/api/models/draft', async route => {
    await new Promise(r => setTimeout(r, 700));
    await route.fulfill({json: {source: fixture + '# delayed draft\n'}});
  });
  await page.getByRole('button', {name: '导入文件', exact: true}).click(); await chooseFile(page);
  await page.getByLabel('我已审核候选类、属性及关系；生成结果仍需业务验证').check();
  await page.getByRole('button', {name: '生成并打开独立草稿'}).click();
  await page.getByRole('link', {name: '业务数据源'}).click();
  await page.waitForTimeout(800);
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.getByRole('link', {name: '模型工作台'}).click();
  await expect(page.getByRole('dialog', {name: '创建独立草稿？'})).toBeVisible();
  await page.getByRole('button', {name: '保留草稿', exact: true}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(fixture);
});
