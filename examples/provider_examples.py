"""
Provider System Examples

This script demonstrates how to use the StartD8 provider plugin system.
"""

import asyncio
from startd8.providers import ProviderRegistry, AgentProvider
from startd8.job_queue import AgentRegistry
from startd8.agents import MockAgent


async def example_1_list_providers():
    """Example 1: Discover and list all available providers"""
    print("\n" + "="*60)
    print("Example 1: List Available Providers")
    print("="*60)
    
    # Auto-discover providers
    ProviderRegistry.discover()
    
    # List all registered providers
    providers = ProviderRegistry.list_providers()
    print(f"\nAvailable providers ({len(providers)}):")
    for provider_name in providers:
        print(f"  - {provider_name}")
    
    # Get detailed info about each provider
    print("\nProvider Details:")
    for provider_name in providers:
        info = ProviderRegistry.get_provider_info(provider_name)
        if info:
            print(f"\n  {info['display_name']} ({info['name']})")
            print(f"    Models: {len(info['models'])}")
            print(f"    Capabilities: {', '.join(info['capabilities'])}")
            print(f"    Streaming: {info['streaming']}")


async def example_2_list_models():
    """Example 2: List all available models from all providers"""
    print("\n" + "="*60)
    print("Example 2: List All Models")
    print("="*60)
    
    all_models = ProviderRegistry.list_all_models()
    
    for provider, models in all_models.items():
        print(f"\n{provider.upper()} ({len(models)} models):")
        for model in models[:5]:  # Show first 5
            print(f"  - {model}")
        if len(models) > 5:
            print(f"  ... and {len(models) - 5} more")


async def example_3_create_agent():
    """Example 3: Create an agent from a provider"""
    print("\n" + "="*60)
    print("Example 3: Create Agent from Provider")
    print("="*60)
    
    # Method 1: Direct provider usage
    print("\nMethod 1: Using ProviderRegistry directly")
    agent = ProviderRegistry.create_agent(
        provider_name="mock",
        model="mock-model",
        name="my-mock-agent"
    )
    print(f"Created agent: {agent.name} ({agent.model})")
    
    # Test the agent
    response_text, time_ms, tokens = await agent.agenerate("Test prompt")
    print(f"Response: {response_text}")
    print(f"Time: {time_ms}ms, Tokens: {tokens.total}")


async def example_4_agent_registry():
    """Example 4: Using AgentRegistry (simpler interface)"""
    print("\n" + "="*60)
    print("Example 4: Using AgentRegistry")
    print("="*60)
    
    registry = AgentRegistry()
    
    # Get agent by model name
    print("\nGetting agent by model name:")
    agent = registry.get_agent("mock-model")
    if agent:
        print(f"Found agent: {agent.name} ({agent.model})")
    
    # Get agent by provider name (uses default model)
    print("\nGetting agent by provider name:")
    agent = registry.get_agent("mock")
    if agent:
        print(f"Found agent: {agent.name} ({agent.model})")
    
    # List all available
    print("\nAll available agents:")
    available = registry.list_available()
    print(f"Total: {len(available)} agents/models available")


async def example_5_find_provider():
    """Example 5: Find which provider supports a model"""
    print("\n" + "="*60)
    print("Example 5: Find Provider for Model")
    print("="*60)
    
    test_models = ["mock-model", "mock-fast", "mock-slow"]
    
    for model in test_models:
        provider = ProviderRegistry.find_provider_for_model(model)
        if provider:
            print(f"\n{model}:")
            print(f"  Provider: {provider.display_name}")
            print(f"  Name: {provider.name}")
            
            # Get model info if available
            info = provider.get_model_info(model)
            if info:
                print(f"  Context window: {info.get('context_window', 'N/A')}")
                print(f"  Cost (input): ${info.get('cost_per_1m_input', 0):.2f}/1M tokens")
        else:
            print(f"\n{model}: No provider found")


async def example_6_parallel_providers():
    """Example 6: Run multiple agents from different providers in parallel"""
    print("\n" + "="*60)
    print("Example 6: Parallel Execution Across Providers")
    print("="*60)
    
    # Create agents from different mock models
    agents = [
        ProviderRegistry.create_agent("mock", "mock-fast", name="fast"),
        ProviderRegistry.create_agent("mock", "mock-model", name="normal"),
        ProviderRegistry.create_agent("mock", "mock-slow", name="slow"),
    ]
    
    print(f"\nRunning {len(agents)} agents in parallel...")
    
    import time
    start = time.time()
    
    # Run all agents in parallel
    tasks = [agent.agenerate("Test prompt") for agent in agents]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start
    
    print(f"\nCompleted in {elapsed:.2f}s")
    for i, (text, time_ms, tokens) in enumerate(results, 1):
        print(f"  Agent {i}: {time_ms}ms, {tokens.total} tokens")


async def example_7_custom_provider():
    """Example 7: Creating and registering a custom provider"""
    print("\n" + "="*60)
    print("Example 7: Custom Provider")
    print("="*60)
    
    # Define a custom provider
    class CustomProvider:
        @property
        def name(self) -> str:
            return "custom"
        
        @property
        def display_name(self) -> str:
            return "Custom Test Provider"
        
        @property
        def supported_models(self):
            return ["custom-v1", "custom-v2"]
        
        def create_agent(self, model: str, name=None, **config):
            return MockAgent(
                name=name or f"custom-{model}",
                model=model
            )
        
        def validate_config(self, config):
            return True
        
        def get_required_env_vars(self):
            return []
        
        def get_capabilities(self):
            return ["text-generation", "custom-feature"]
        
        def supports_streaming(self):
            return False
        
        def get_model_info(self, model: str):
            return {
                "name": f"Custom {model}",
                "context_window": 100000,
                "cost_per_1m_input": 1.00,
                "cost_per_1m_output": 2.00
            }
    
    # Register the custom provider
    custom = CustomProvider()
    ProviderRegistry.register(custom)
    
    print("\nRegistered custom provider!")
    print(f"Name: {custom.name}")
    print(f"Display: {custom.display_name}")
    print(f"Models: {custom.supported_models}")
    
    # Use the custom provider
    agent = ProviderRegistry.create_agent(
        provider_name="custom",
        model="custom-v1"
    )
    
    print(f"\nCreated custom agent: {agent.name}")
    response = await agent.agenerate("Test")
    print(f"Response: {response[0]}")
    
    # Clean up
    ProviderRegistry.clear()
    ProviderRegistry.discover()  # Re-discover built-ins


async def example_8_model_metadata():
    """Example 8: Using model metadata"""
    print("\n" + "="*60)
    print("Example 8: Model Metadata")
    print("="*60)
    
    provider = ProviderRegistry.get_provider("mock")
    if not provider:
        print("Mock provider not available")
        return
    
    models = ["mock-model", "mock-fast", "mock-slow"]
    
    print("\nModel Metadata:")
    for model in models:
        info = provider.get_model_info(model)
        if info:
            print(f"\n{model}:")
            for key, value in info.items():
                print(f"  {key}: {value}")


async def example_9_error_handling():
    """Example 9: Error handling with providers"""
    print("\n" + "="*60)
    print("Example 9: Error Handling")
    print("="*60)
    
    from startd8.exceptions import ConfigurationError
    
    # Try to use nonexistent provider
    print("\n1. Nonexistent provider:")
    try:
        agent = ProviderRegistry.create_agent(
            provider_name="nonexistent",
            model="some-model"
        )
    except ConfigurationError as e:
        print(f"   Error (expected): {e}")
    
    # Try to use unsupported model
    print("\n2. Unsupported model:")
    try:
        agent = ProviderRegistry.create_agent(
            provider_name="mock",
            model="unsupported-model"
        )
    except ValueError as e:
        print(f"   Error (expected): {e}")
    
    # Handle missing provider gracefully
    print("\n3. Graceful handling:")
    provider = ProviderRegistry.get_provider("nonexistent")
    if provider is None:
        print("   Provider not found, falling back to mock")
        provider = ProviderRegistry.get_provider("mock")
        agent = provider.create_agent("mock-model")
        print(f"   Using fallback: {agent.name}")


async def example_10_provider_capabilities():
    """Example 10: Checking provider capabilities"""
    print("\n" + "="*60)
    print("Example 10: Provider Capabilities")
    print("="*60)
    
    for provider_name in ProviderRegistry.list_providers():
        provider = ProviderRegistry.get_provider(provider_name)
        if provider:
            print(f"\n{provider.display_name}:")
            
            caps = provider.get_capabilities()
            print(f"  Capabilities: {', '.join(caps)}")
            
            print(f"  Streaming: {'Yes' if provider.supports_streaming() else 'No'}")
            
            # Check for specific capabilities
            if 'vision' in caps:
                print("  ✅ Supports vision/image understanding")
            if 'long-context' in caps or 'ultra-long-context' in caps:
                print("  ✅ Supports extended context windows")


async def main():
    """Run all examples"""
    print("\n" + "🚀 StartD8 Provider System Examples ".center(60, "="))
    
    examples = [
        example_1_list_providers,
        example_2_list_models,
        example_3_create_agent,
        example_4_agent_registry,
        example_5_find_provider,
        example_6_parallel_providers,
        example_7_custom_provider,
        example_8_model_metadata,
        example_9_error_handling,
        example_10_provider_capabilities,
    ]
    
    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"\n❌ Error in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("All examples completed! ✅")
    print("="*60)
    print("\nKey Takeaways:")
    print("1. Providers are discovered automatically")
    print("2. Multiple ways to create agents (Registry or Provider)")
    print("3. Easy to add custom providers")
    print("4. Rich metadata for models")
    print("5. Graceful error handling")
    print("\nTry modifying these examples to explore more!")


if __name__ == "__main__":
    asyncio.run(main())
