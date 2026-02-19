#!/usr/bin/env python3
"""
Verification script for Orderly Agent SDK integrations.
Tests that imports work correctly and provides installation guidance.
"""

def test_core_imports():
    """Test core integration imports"""
    print("🔧 Testing core imports...")
    
    try:
        from orderly_agent.integrations._client import OrderlyConfig, OrderlyClient
        print("✅ Core client imports OK")
    except ImportError as e:
        print(f"❌ Core client import failed: {e}")
        return False
        
    try:
        import orderly_agent.integrations
        print("✅ Integrations package import OK")
    except ImportError as e:
        print(f"❌ Integrations package import failed: {e}")
        return False
    
    return True

def test_langchain_integration():
    """Test LangChain integration"""
    print("\n🦜 Testing LangChain integration...")
    
    try:
        from orderly_agent.integrations.langchain import get_orderly_tools
        tools = get_orderly_tools()
        print(f"✅ LangChain integration OK - {len(tools)} tools loaded")
        return True
    except ImportError as e:
        print(f"⚠️  LangChain not available: {e}")
        print("   Install with: pip install 'agent-trading-sdk[langchain]'")
        return False

def test_crewai_integration():
    """Test CrewAI integration"""
    print("\n🚢 Testing CrewAI integration...")
    
    try:
        from orderly_agent.integrations.crewai import ORDERLY_TOOLS, orderly_trader_agent
        tools = ORDERLY_TOOLS
        print(f"✅ CrewAI integration OK - {len(tools)} tools loaded")
        
        # Test agent creation (but don't initialize fully without CrewAI installed)
        print("✅ CrewAI trader agent available")
        return True
    except ImportError as e:
        print(f"⚠️  CrewAI not available: {e}")
        print("   Install with: pip install 'agent-trading-sdk[crewai]'")
        return False

def test_autogen_integration():
    """Test AutoGen integration"""
    print("\n🤖 Testing AutoGen integration...")
    
    try:
        from orderly_agent.integrations.autogen import register_orderly_tools
        print("✅ AutoGen integration OK - registration function available")
        return True
    except ImportError as e:
        print(f"⚠️  AutoGen not available: {e}")
        print("   Install with: pip install 'agent-trading-sdk[autogen]'")
        return False

def main():
    """Run all tests"""
    print("🧪 Orderly Agent SDK Integration Tests\n")
    
    # Test core functionality
    if not test_core_imports():
        print("\n❌ Core imports failed - cannot proceed")
        return
    
    # Test integrations (these may fail if frameworks aren't installed)
    langchain_ok = test_langchain_integration()
    crewai_ok = test_crewai_integration() 
    autogen_ok = test_autogen_integration()
    
    # Summary
    print(f"\n📊 Test Results Summary:")
    print(f"   Core SDK: ✅ Working")
    print(f"   LangChain: {'✅' if langchain_ok else '⚠️'} {'Working' if langchain_ok else 'Not installed'}")
    print(f"   CrewAI: {'✅' if crewai_ok else '⚠️'} {'Working' if crewai_ok else 'Not installed'}")
    print(f"   AutoGen: {'✅' if autogen_ok else '⚠️'} {'Working' if autogen_ok else 'Not installed'}")
    
    if not any([langchain_ok, crewai_ok, autogen_ok]):
        print(f"\n💡 Quick Start:")
        print(f"   pip install 'agent-trading-sdk[all-integrations]'  # Install all")
        print(f"   pip install 'agent-trading-sdk[langchain]'         # Just LangChain")
        print(f"   pip install 'agent-trading-sdk[crewai]'            # Just CrewAI")
        print(f"   pip install 'agent-trading-sdk[autogen]'           # Just AutoGen")
    
    print(f"\n🚀 Ready to build AI trading agents!")

if __name__ == "__main__":
    main()