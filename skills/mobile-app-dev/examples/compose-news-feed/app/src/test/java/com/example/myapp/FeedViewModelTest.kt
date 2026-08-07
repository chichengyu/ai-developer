package com.example.myapp

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FeedViewModelTest {
    @Test
    fun `initial state is Loading`() {
        val vm = FeedViewModel(repository = StubFeedRepository())
        assertTrue(vm.uiState.value is FeedUiState.Loading)
    }

    @Test
    fun `refresh emits Loaded with items`() {
        val vm = FeedViewModel(repository = StubFeedRepository())
        vm.refresh()
        val state = vm.uiState.value
        assertTrue("expected Loaded, got $state", state is FeedUiState.Loaded)
        assertEquals(2, (state as FeedUiState.Loaded).items.size)
    }
}