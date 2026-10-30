import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const source='id: https://example.test/model\nname: sample\n';
async function setup(page: Page, options: {forced?: boolean; delayedUnauthorized?: boolean} = {}) {
  let signedIn=false, forced=options.forced ?? true, csrf='csrf-first';
  const seen: string[]=[];
  const session=() => ({user:{id:'user-1',username:'admin',must_change_password:forced},csrf_token:csrf,insecure_http:true});
  await page.route('**/*', async route => {
    const url=new URL(route.request().url());
    if (!url.pathname.startsWith('/api/')) {
      const name=url.pathname.startsWith('/assets/') || url.pathname==='/theme.js' ? url.pathname : '/index.html';
      const file=path.join(process.cwd(),'dist',name);
      await route.fulfill({body:await fs.readFile(file),contentType:file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html'});return;
    }
    let status=200, body: unknown={};
    const unauthorized={detail:{message:'请先登录。',code:'unauthenticated'}};
    if (url.pathname==='/api/auth/me') {status=signedIn?200:401;body=signedIn?session():unauthorized;}
    else if (url.pathname==='/api/auth/login') {
      const input=route.request().postDataJSON();
      if (input.password==='bad') {status=401;body={detail:{message:'用户名或密码错误。',code:'invalid_credentials'}};}
      else {signedIn=true;body=session();}
    } else if (url.pathname==='/api/auth/password') {
      expect(route.request().headers()['x-csrf-token']).toBe(csrf);
      forced=false;csrf='csrf-rotated';body=session();
    } else if (url.pathname==='/api/auth/logout') {
      expect(route.request().headers()['x-csrf-token']).toBe(csrf);
      signedIn=false;body={ok:true};
    } else {
      seen.push(url.pathname);
      if (!signedIn) {status=401;body=unauthorized;}
      else if (forced) {status=403;body={detail:{message:'必须改密。',code:'password_change_required'}};}
      else if (url.pathname==='/api/system') body={database_configured:true,mode:'authenticated',version:'0.2.0',insecure_http:true};
      else if (url.pathname==='/api/models/template') body={source,saved:false};
      else if (url.pathname==='/api/models') body={items:[]};
      else if (url.pathname==='/api/models/validate' && options.delayedUnauthorized) {
        await new Promise(r=>setTimeout(r,1200));status=401;body=unauthorized;
      } else body={items:[]};
    }
    await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('/models');
  await expect(page.getByRole('heading',{name:'登录本体工作台'})).toBeVisible();
  return seen;
}

async function login(page: Page) {
  await page.getByLabel('用户名',{exact:true}).fill('admin');
  await page.getByLabel('密码',{exact:true}).fill('Synthetic-Temporary-Password!');
  await page.getByRole('button',{name:'登录',exact:true}).click();
}

for (const width of [1440,375,320]) {
  for (const theme of ['dark','light']) {
    test(`login ${width} ${theme}`, async ({page}) => {
      await page.setViewportSize({width,height:850});
      const seen=await setup(page);
      if (theme==='light') await page.getByRole('button',{name:'切换浅色主题'}).click();
      expect(seen).toHaveLength(0);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
      if (width===1440 || width===375) await page.screenshot({path:`test-results/login-${width}-${theme}.png`,fullPage:true});
    });
  }
}

test('first login cannot load business data until password changed',async ({page}) => {
  const seen=await setup(page);
  await login(page);
  await expect(page.getByRole('heading',{name:'设置你的登录密码'})).toBeVisible();
  expect(seen).toHaveLength(0);
  await page.getByLabel('临时密码',{exact:true}).fill('Synthetic-Temporary-Password!');
  await page.getByLabel('新密码',{exact:true}).fill('A-new-very-long-passphrase!');
  await page.getByLabel('确认新密码',{exact:true}).fill('A-new-very-long-passphrase!');
  await page.getByRole('button',{name:'确认修改密码'}).click();
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(source);
  expect(seen).toContain('/api/models/template');
  const storage=await page.evaluate(()=>({local:{...localStorage},session:{...sessionStorage}}));
  expect(JSON.stringify(storage)).not.toMatch(/Synthetic|csrf|token|passphrase/);
});

test('bad credentials stay on login and do not reveal business data',async ({page}) => {
  const seen=await setup(page);
  await page.getByLabel('密码',{exact:true}).fill('bad');
  await page.getByRole('button',{name:'登录',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('用户名或密码错误');
  await expect(page.getByLabel('密码',{exact:true})).toHaveValue('');
  expect(seen).toHaveLength(0);
});

test('logout clears workspace and late old 401 does not log out new session',async ({page}) => {
  await setup(page,{forced:false,delayedUnauthorized:true});
  await login(page);
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(source);
  await page.getByRole('button',{name:'校验模型',exact:true}).click();
  await page.getByRole('button',{name:'退出',exact:true}).click();
  await page.getByRole('button',{name:'放弃草稿并退出'}).click();
  await expect(page.getByRole('heading',{name:'登录本体工作台'})).toBeVisible();
  await expect(page.getByLabel('LinkML 模型源码')).not.toBeVisible();
  await login(page);
  await expect(page.getByLabel('LinkML 模型源码')).toHaveValue(source);
  await page.waitForTimeout(1400);
  await expect(page.getByLabel('LinkML 模型源码')).toBeVisible();
});

test('normal account password change remains accessible after login',async ({page}) => {
  await setup(page,{forced:false});await login(page);
  await page.getByRole('link',{name:'账户安全'}).click();
  await page.getByLabel('当前密码',{exact:true}).fill('Synthetic-Temporary-Password!');
  await page.getByLabel('新密码',{exact:true}).fill('Another-long-account-passphrase!');
  await page.getByLabel('确认新密码',{exact:true}).fill('Another-long-account-passphrase!');
  await page.getByRole('button',{name:'确认修改密码'}).click();
  await expect(page.getByText('密码已修改，其他会话已失效。')).toBeVisible();
});
