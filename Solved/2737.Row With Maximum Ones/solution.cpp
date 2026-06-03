class Solution {
public:
    vector<int> rowAndMaximumOnes(vector<vector<int>>& mat) {
        int n = mat.size();
        int m = mat[0].size();
        
        vector<int> row(n);


        for(int i=0;i<n;i++){
            int count = 0;
            for(int j=0;j<m;j++){
                if(mat[i][j]==1){
                    count++;
                }
            }
            row[i] = count;
        }
        int max_ = 0;
        int idi = 0;
        for(int i=0;i<n;i++){
            if(max_<row[i]){
                max_ = row[i];
                idi = i;
            }
        }
        return {idi,max_};
    }
};