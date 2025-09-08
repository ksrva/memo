import { test, expect } from '@playwright/test';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/v1';

test.describe('Memory Recall Scenarios', () => {
  
  test('recall related memos on return visit', async () => {
    // First visit: Create and save a memo about TypeScript
    const firstVisitData = {
      url: 'https://blog.example.com/typescript-best-practices',
      title: 'TypeScript Best Practices for Large Applications',
      main_text: `
        TypeScript has become essential for large-scale JavaScript applications.
        Key practices include:
        - Use strict mode for better type safety
        - Leverage union types and generics
        - Implement proper error handling
        - Use interfaces for object shapes
        - Configure tsconfig.json properly
      `,
      selection: 'union types and generics',
      goal: 'Learn TypeScript advanced patterns'
    };

    // Generate and save first memo
    const composeResponse1 = await axios.post(`${API_BASE}/compose`, firstVisitData);
    const summarizeResponse1 = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: composeResponse1.data.context_bundle,
      goal: firstVisitData.goal
    });

    const memo1 = summarizeResponse1.data;
    
    // Save to memory
    await axios.post(`${API_BASE}/memory/upsert`, {
      url: firstVisitData.url,
      title: firstVisitData.title,
      text: memo1.markdown,
      tags: memo1.entities.slice(0, 5),
      ts: Math.floor(Date.now() / 1000)
    });

    // Wait for embedding processing
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Second visit: Related TypeScript content should recall first memo
    const secondVisitData = {
      url: 'https://blog.example.com/typescript-generics-guide',
      title: 'Complete Guide to TypeScript Generics',
      main_text: `
        TypeScript generics provide a way to create reusable code components.
        Generics allow you to write functions and classes that work with multiple types.
        
        Basic syntax:
        function identity<T>(arg: T): T { return arg; }
        
        Advanced patterns:
        - Conditional types
        - Mapped types  
        - Template literal types
        - Type constraints with extends
      `,
      selection: 'Conditional types',
      goal: 'Master advanced TypeScript generics'
    };

    // Generate context for second visit
    const composeResponse2 = await axios.post(`${API_BASE}/compose`, secondVisitData);
    
    // Should include memory from first visit
    const contextBundle2 = composeResponse2.data.context_bundle;
    expect(contextBundle2.memories.length).toBeGreaterThan(0);
    
    const relatedMemory = contextBundle2.memories.find((mem: any) => 
      mem.text.toLowerCase().includes('typescript') || 
      mem.text.toLowerCase().includes('type')
    );
    
    expect(relatedMemory).toBeDefined();
    expect(relatedMemory.score).toBeGreaterThan(0.5);
  });

  test('search memories by semantic similarity', async () => {
    // Create several memos with different topics
    const memos = [
      {
        url: 'https://example.com/react-hooks',
        title: 'React Hooks Tutorial',
        text: 'React hooks like useState and useEffect provide a way to use state in functional components.',
        tags: ['react', 'hooks', 'javascript']
      },
      {
        url: 'https://example.com/python-ml',
        title: 'Python Machine Learning Guide',
        text: 'Python is excellent for machine learning with libraries like scikit-learn, pandas, and numpy.',
        tags: ['python', 'ml', 'data-science']
      },
      {
        url: 'https://example.com/vue-components',
        title: 'Vue Component Patterns',
        text: 'Vue.js components can be composed using props, slots, and composition API for reusability.',
        tags: ['vue', 'javascript', 'frontend']
      }
    ];

    // Store all memos
    for (const memo of memos) {
      await axios.post(`${API_BASE}/memory/upsert`, {
        ...memo,
        ts: Math.floor(Date.now() / 1000)
      });
    }

    // Wait for embeddings
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Search for React-related content
    const reactSearchResponse = await axios.get(`${API_BASE}/memory/search?q=React components functional state&k=5`);
    expect(reactSearchResponse.status).toBe(200);
    
    const reactResults = reactSearchResponse.data.hits;
    expect(reactResults.length).toBeGreaterThan(0);
    
    const reactMemo = reactResults.find((hit: any) => hit.text.includes('React'));
    expect(reactMemo).toBeDefined();
    expect(reactMemo.score).toBeGreaterThan(0.6);

    // Search for Python ML content
    const mlSearchResponse = await axios.get(`${API_BASE}/memory/search?q=Python machine learning data science&k=5`);
    const mlResults = mlSearchResponse.data.hits;
    
    const mlMemo = mlResults.find((hit: any) => hit.text.includes('machine learning'));
    expect(mlMemo).toBeDefined();

    // Search for frontend frameworks
    const frontendSearchResponse = await axios.get(`${API_BASE}/memory/search?q=frontend framework components JavaScript&k=5`);
    const frontendResults = frontendSearchResponse.data.hits;
    
    expect(frontendResults.length).toBeGreaterThan(0);
    // Should find both React and Vue results
    const hasReactOrVue = frontendResults.some((hit: any) => 
      hit.text.includes('React') || hit.text.includes('Vue')
    );
    expect(hasReactOrVue).toBe(true);
  });

  test('memory enriches context bundle on subsequent visits', async () => {
    // Create initial memo about API design
    const initialMemo = {
      url: 'https://docs.api-design.com/rest-principles',
      title: 'REST API Design Principles', 
      text: `
        # REST API Design Memo
        
        ## Summary
        REST APIs should follow consistent patterns for URLs, HTTP methods, and response formats.
        
        ## Key Entities
        - HTTP Methods: GET, POST, PUT, DELETE
        - Status Codes: 200, 404, 500
        - JSON responses
        
        ## Next Steps
        1. Design URL structure
        2. Define response schemas
        3. Implement error handling
      `,
      tags: ['api', 'rest', 'design'],
      ts: Math.floor(Date.now() / 1000)
    };

    await axios.post(`${API_BASE}/memory/upsert`, initialMemo);
    
    // Wait for embedding
    await new Promise(resolve => setTimeout(resolve, 1000));

    // Visit related page about GraphQL
    const newPageData = {
      url: 'https://docs.api-design.com/graphql-vs-rest',
      title: 'GraphQL vs REST API Comparison',
      main_text: `
        GraphQL and REST are two different approaches to API design.
        GraphQL provides a query language for APIs and allows clients to request specific data.
        REST uses HTTP methods and resource-based URLs.
        
        Pros of GraphQL:
        - Single endpoint
        - Flexible queries
        - Strong typing
        
        Pros of REST:
        - Simple and well-understood
        - HTTP caching
        - Stateless
      `,
      selection: '',
      goal: 'Compare API approaches and decide which to use'
    };

    const composeResponse = await axios.post(`${API_BASE}/compose`, newPageData);
    const contextBundle = composeResponse.data.context_bundle;

    // Should include the related REST API memo
    expect(contextBundle.memories.length).toBeGreaterThan(0);
    
    const apiMemory = contextBundle.memories.find((mem: any) => 
      mem.text.toLowerCase().includes('rest') || mem.text.toLowerCase().includes('api')
    );
    
    expect(apiMemory).toBeDefined();
    expect(apiMemory.why).toContain('similarity');

    // Generate new memo with enriched context
    const summarizeResponse = await axios.post(`${API_BASE}/summarize`, {
      context_bundle: contextBundle,
      goal: newPageData.goal
    });

    const enrichedMemo = summarizeResponse.data;
    
    // Should reference both GraphQL and REST concepts
    expect(enrichedMemo.summary).toMatch(/GraphQL.*REST|REST.*GraphQL/i);
    expect(enrichedMemo.entities).toEqual(
      expect.arrayContaining(['GraphQL', 'REST'])
    );
  });

  test('memory recall accuracy meets 60% threshold', async () => {
    // Create 10 diverse memos
    const testMemos = [
      { topic: 'javascript', text: 'JavaScript async/await patterns for handling promises' },
      { topic: 'python', text: 'Python data structures: lists, dictionaries, sets' },
      { topic: 'react', text: 'React state management with Redux and Context API' },
      { topic: 'nodejs', text: 'Node.js Express server setup and middleware configuration' },
      { topic: 'docker', text: 'Docker containerization for microservices architecture' },
      { topic: 'sql', text: 'SQL query optimization and database indexing strategies' },
      { topic: 'git', text: 'Git branching strategies and merge conflict resolution' },
      { topic: 'testing', text: 'Unit testing with Jest and integration testing patterns' },
      { topic: 'css', text: 'CSS Grid and Flexbox layout techniques for responsive design' },
      { topic: 'security', text: 'Web application security: HTTPS, CSRF protection, input validation' }
    ];

    // Store all memos
    for (let i = 0; i < testMemos.length; i++) {
      const memo = testMemos[i];
      await axios.post(`${API_BASE}/memory/upsert`, {
        url: `https://example.com/${memo.topic}-guide`,
        title: `${memo.topic.toUpperCase()} Guide`,
        text: memo.text,
        tags: [memo.topic],
        ts: Math.floor(Date.now() / 1000) - i  // Different timestamps
      });
    }

    // Wait for all embeddings
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Test recall accuracy with related queries
    const testQueries = [
      { query: 'JavaScript promises async programming', expectedTopic: 'javascript' },
      { query: 'Python lists data structures', expectedTopic: 'python' },
      { query: 'React Redux state management', expectedTopic: 'react' },
      { query: 'Express Node.js server', expectedTopic: 'nodejs' },
      { query: 'container microservices Docker', expectedTopic: 'docker' },
      { query: 'database SQL optimization', expectedTopic: 'sql' },
      { query: 'version control Git branches', expectedTopic: 'git' },
      { query: 'Jest testing unit tests', expectedTopic: 'testing' },
      { query: 'responsive CSS layout Grid', expectedTopic: 'css' },
      { query: 'web security HTTPS CSRF', expectedTopic: 'security' }
    ];

    let correctRecalls = 0;

    for (const testQuery of testQueries) {
      const searchResponse = await axios.get(
        `${API_BASE}/memory/search?q=${encodeURIComponent(testQuery.query)}&k=3`
      );
      
      const results = searchResponse.data.hits;
      
      // Check if top result matches expected topic
      if (results.length > 0) {
        const topResult = results[0];
        if (topResult.text.toLowerCase().includes(testQuery.expectedTopic) && 
            topResult.score > 0.5) {
          correctRecalls++;
        }
      }
    }

    const recallRate = correctRecalls / testQueries.length;
    console.log(`Memory recall rate: ${(recallRate * 100).toFixed(1)}%`);
    
    // Should meet 60% threshold
    expect(recallRate).toBeGreaterThanOrEqual(0.6);
  });
});