class Solution {
public:
    // bool anagram(string s, string t){
    //     int ns = s.size();
    //     int nt = t.size();
    //     if (ns!=nt) {
    //         return false;
    //     }
    //     vector<int> rs(26,0);
    //     vector<int> rt(26,0);

    //     for(int i=0; i<ns; i++) {
    //         rs[s[i]-'a']++;
    //         rt[t[i]-'a']++;
    //     }
    //     return rs==rt;
    // }
    vector<vector<string>> groupAnagrams(vector<string>& strs) {
        // vector<vector<string>> res;
        int n = strs.size();

        map<vector<int>, vector<string>> rec;

        for(int i=0;i<n;i++){
            vector<int> hash(26,0);
            for(char c:strs[i]) {
                hash[c-'a']++;
            }
            rec[hash].push_back(strs[i]);
        }
        vector<vector<string>> res;
        for(auto [key,val]: rec){
            res.push_back(val);
        }
        return res;        
    }
};