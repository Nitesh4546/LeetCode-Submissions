class Solution(object):
    def permute(self, nums):
        """
        :type nums: List[int]
        :rtype: List[List[int]]
        """
        ans = []
        used = [False] * len(nums)
        def dfs(path):
          if len(path) == len(nums):
            ans.append(path[:])
            return
          for i, num in enumerate(nums):
            if used[i]:
              continue
            used[i] = True
            path.append(num)
            dfs(path)
            path.pop()
            used[i] = False
        dfs([])
        return ans
        