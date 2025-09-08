import { test, expect } from '@playwright/test';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/v1';

test.describe('Memo API Endpoints', () => {
  test('health check', async () => {
    const response = await axios.get(`${API_BASE}/health`);
    expect(response.status).toBe(200);
    expect(response.data.status).toBe('healthy');
  });

  test('compose context from page data', async () => {
    const testData = {
      url: 'https://jobs.example.com/typescript-engineer',
      title: 'Senior TypeScript Engineer',
      main_text: 'We are looking for a senior TypeScript engineer to join our team building AI-powered tools. Requirements: 5+ years experience with TypeScript, React, Node.js. Experience with LLMs preferred. Competitive salary $150K-200K.',
      selection: 'AI-powered tools',
      dom_map: [
        { role: 'button', text: 'Apply Now', selector: 'button.apply' }
      ],
      recent_events: [
        { type: 'click', text: 'Careers', ts: Date.now() }
      ],
      goal: 'Extract job requirements and create application checklist'
    };

    const response = await axios.post(`${API_BASE}/compose`, testData);
    
    expect(response.status).toBe(200);
    expect(response.data).toHaveProperty('context_bundle');
    expect(response.data.context_bundle).toHaveProperty('summary_hint');
    expect(response.data.context_bundle).toHaveProperty('entities_hint');
    expect(response.data.context_bundle).toHaveProperty('salient_sections');
    expect(response.data.context_bundle.entities_hint).toContain('TypeScript');
  });

  test('summarize context bundle', async () => {
    const contextBundle = {
      summary_hint: 'Senior TypeScript Engineer job at AI company',
      entities_hint: ['TypeScript', 'React', 'Node.js', 'AI', '$150K-200K'],
      salient_sections: [
        {
          text: 'We are looking for a senior TypeScript engineer to join our team building AI-powered tools.',
          score: 0.9
        },
        {
          text: 'Requirements: 5+ years experience with TypeScript, React, Node.js.',
          score: 0.85
        }
      ],
      memories: []
    };

    const response = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: contextBundle,
      goal: 'Extract job requirements and create application checklist'
    });

    expect(response.status).toBe(200);
    expect(response.data).toHaveProperty('summary');
    expect(response.data).toHaveProperty('entities');
    expect(response.data).toHaveProperty('tasks');
    expect(response.data).toHaveProperty('risks');
    expect(response.data).toHaveProperty('markdown');
    
    // Validate content quality
    expect(response.data.summary.length).toBeGreaterThan(10);
    expect(response.data.entities.length).toBeGreaterThan(0);
    expect(response.data.tasks.length).toBeGreaterThan(0);
    expect(response.data.markdown).toContain('# Memo');
  });

  test('memory upsert and search', async () => {
    // First, upsert a memory
    const memoData = {
      url: 'https://example.com/test-job',
      title: 'Test Job Posting',
      text: 'This is a test job posting for a TypeScript developer with React experience.',
      tags: ['job', 'typescript', 'react'],
      ts: Math.floor(Date.now() / 1000)
    };

    const upsertResponse = await axios.post(`${API_BASE}/memory/upsert`, memoData);
    expect(upsertResponse.status).toBe(200);
    expect(upsertResponse.data).toHaveProperty('id');

    // Wait a moment for embedding to be processed
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Then search for it
    const searchResponse = await axios.get(`${API_BASE}/memory/search?q=TypeScript developer React&k=5`);
    expect(searchResponse.status).toBe(200);
    expect(searchResponse.data).toHaveProperty('hits');
    expect(searchResponse.data.hits.length).toBeGreaterThan(0);
    
    const foundMemo = searchResponse.data.hits.find((hit: any) => 
      hit.text.includes('TypeScript developer')
    );
    expect(foundMemo).toBeDefined();
  });

  test('metrics endpoint', async () => {
    const response = await axios.get(`${API_BASE}/metrics`);
    expect(response.status).toBe(200);
    expect(response.data).toContain('memo_latency_p95');
    expect(response.data).toContain('memo_tokens_total');
    expect(response.data).toContain('memo_success_rate');
  });
});