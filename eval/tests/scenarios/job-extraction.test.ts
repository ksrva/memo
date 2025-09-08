import { test, expect } from '@playwright/test';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/v1';

test.describe('Job Posting Extraction Scenarios', () => {
  
  test('extract requirements from tech job posting', async () => {
    const jobPageData = {
      url: 'https://jobs.techcorp.com/senior-fullstack-engineer',
      title: 'Senior Full-Stack Engineer - AI Platform',
      main_text: `
        TechCorp is seeking a Senior Full-Stack Engineer to join our AI Platform team.
        
        Responsibilities:
        - Build scalable web applications using React and TypeScript
        - Develop APIs with Node.js and Python
        - Work with machine learning models and LLMs
        - Collaborate with cross-functional teams
        
        Requirements:
        - 5+ years of software engineering experience
        - Expert knowledge of TypeScript/JavaScript and React
        - Experience with Python and ML frameworks
        - Strong system design skills
        - Bachelor's degree in Computer Science or equivalent
        
        Nice to have:
        - Experience with OpenAI APIs or similar LLM platforms
        - Knowledge of vector databases
        - DevOps experience with Docker/Kubernetes
        
        Compensation: $160K - $220K base salary plus equity
        Benefits: Health, dental, vision, 401k matching, unlimited PTO
      `,
      selection: 'Requirements',
      goal: 'Extract job requirements and create application strategy'
    };

    // Step 1: Compose context
    const composeResponse = await axios.post(`${API_BASE}/compose`, jobPageData);
    expect(composeResponse.status).toBe(200);
    
    const contextBundle = composeResponse.data.context_bundle;
    expect(contextBundle.entities_hint).toEqual(
      expect.arrayContaining(['TypeScript', 'React', 'Python'])
    );

    // Step 2: Generate memo
    const summarizeResponse = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: contextBundle,
      goal: jobPageData.goal
    });

    expect(summarizeResponse.status).toBe(200);
    
    const memo = summarizeResponse.data;
    
    // Validate memo quality
    expect(memo.summary).toContain('Senior Full-Stack Engineer');
    expect(memo.summary).toContain('AI Platform');
    
    expect(memo.entities).toEqual(
      expect.arrayContaining(['TechCorp', 'TypeScript', 'React', 'Python'])
    );
    
    expect(memo.tasks).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/resume|application/i),
        expect.stringMatching(/portfolio|projects/i)
      ])
    );
    
    expect(memo.risks.length).toBeGreaterThan(0);
    
    // Check that salary range is captured
    expect(memo.summary || memo.entities.join(' ')).toMatch(/160K|220K|\$160|\$220/);
  });

  test('create memo for documentation page', async () => {
    const docPageData = {
      url: 'https://docs.fastapi.com/tutorial/first-steps',
      title: 'FastAPI Tutorial - First Steps',
      main_text: `
        FastAPI is a modern web framework for building APIs with Python 3.7+.
        
        Key features:
        - Fast: Very high performance, on par with NodeJS and Go
        - Fast to code: Increase development speed by 200-300%
        - Fewer bugs: Reduce human errors by 40%
        - Intuitive: Editor support with completion everywhere
        - Easy: Designed to be easy to use and learn
        - Short: Minimize code duplication
        - Robust: Get production-ready code with automatic docs
        - Standards-based: Based on OpenAPI and JSON Schema
        
        Installation:
        pip install fastapi
        pip install "uvicorn[standard]"
        
        Basic example:
        from fastapi import FastAPI
        app = FastAPI()
        
        @app.get("/")
        def read_root():
            return {"Hello": "World"}
      `,
      selection: 'Key features',
      goal: 'Learn FastAPI basics and create learning plan'
    };

    // Full flow test
    const composeResponse = await axios.post(`${API_BASE}/compose`, docPageData);
    const summarizeResponse = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: composeResponse.data.context_bundle,
      goal: docPageData.goal
    });

    const memo = summarizeResponse.data;
    
    expect(memo.summary).toContain('FastAPI');
    expect(memo.entities).toContain('Python');
    expect(memo.tasks).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/install|setup/i),
        expect.stringMatching(/tutorial|example/i)
      ])
    );
  });

  test('process news article for key insights', async () => {
    const newsData = {
      url: 'https://techcrunch.com/ai-startup-funding',
      title: 'AI Startup Raises $50M Series B',
      main_text: `
        VectorAI, a startup building enterprise AI search tools, announced today 
        it has raised $50 million in Series B funding led by Andreessen Horowitz.
        
        The company, founded in 2022, helps enterprises search through unstructured 
        data using vector embeddings and large language models. Their platform 
        integrates with existing tools like Slack, Notion, and Google Workspace.
        
        "We're seeing massive demand from enterprises who want to unlock insights 
        from their data silos," said CEO Sarah Chen. The funding will be used to 
        expand the engineering team and accelerate product development.
        
        VectorAI competes with companies like Pinecone and Weaviate in the 
        vector database space. The company has 50+ enterprise customers including 
        Fortune 500 companies.
      `,
      selection: 'vector embeddings and large language models',
      goal: 'Analyze competitive landscape and market trends'
    };

    const composeResponse = await axios.post(`${API_BASE}/compose`, newsData);
    const summarizeResponse = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: composeResponse.data.context_bundle,
      goal: newsData.goal
    });

    const memo = summarizeResponse.data;
    
    expect(memo.entities).toEqual(
      expect.arrayContaining(['VectorAI', 'Andreessen Horowitz', '$50M'])
    );
    
    expect(memo.summary).toContain('Series B');
    expect(memo.tasks).toEqual(
      expect.arrayContaining([
        expect.stringMatching(/research|analyze/i)
      ])
    );
  });

  test('end-to-end latency under 2.5 seconds', async () => {
    const testData = {
      url: 'https://example.com/test-page',
      title: 'Test Page',
      main_text: 'This is a test page with some content about TypeScript and React development.',
      selection: '',
      goal: 'Create a quick memo'
    };

    const startTime = Date.now();

    // Full compose + summarize flow
    const composeResponse = await axios.post(`${API_BASE}/compose`, testData);
    const summarizeResponse = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: composeResponse.data.context_bundle,
      goal: testData.goal
    });

    const endTime = Date.now();
    const latency = endTime - startTime;

    // Should complete within 2.5 seconds
    expect(latency).toBeLessThan(2500);
    expect(summarizeResponse.status).toBe(200);
  });
});